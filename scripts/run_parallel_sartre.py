#!/usr/bin/env python3
"""
================================================================================
run_parallel_sartre.py

Parallel Monte Carlo Event Generator Orchestrator for Sartre 2
Analysis of J/psi Photoproduction in p+p Collisions at sqrt(s) = 510 GeV
Author: Štěpán Skalka (CTU in Prague)

================================================================================
ARCHITECTURE & HOW THE MULTI-CORE ORCHESTRATION WORKS:
================================================================================
Generating large Monte Carlo samples (e.g., 100,000 events) using Sartre's
Color Dipole Model can require several hours on a single CPU core because each
event evaluates multidimensional numerical integrations and dipole amplitude
interpolations.

This Python script orchestrates parallel execution across multiple CPU cores
while maintaining strict scientific rigor and computational safety:

1. WORKER PARTITIONING:
   The user requests a total number of events (e.g. 100,000) and worker processes
   (e.g. 12). The script divides the total events evenly across workers:
       events_per_worker = total_events // num_workers
   Any remainder is distributed among the first few workers, ensuring that the
   exact requested event count is simulated.

2. STATISTICALLY INDEPENDENT RANDOM SEEDS:
   To prevent duplicate Monte Carlo events across worker processes, each worker k
   receives a strictly disjoint, deterministic random seed:
       Seed_k = BaseSeed + 100 * k
   Because CERN ROOT's TRandom3 generator has a period of 2^19937 - 1, separate
   seeds ensure that every worker explores completely uncorrelated pseudo-random
   phase-space trajectories.

3. RESOURCE PROTECTION & SYSTEM RESPONSIVENESS:
   - Worker processes are executed with `nice -n 10` scheduling priority,
     guaranteeing that the operating system remains responsive for desktop
     and shell tasks.
   - The script caps the maximum worker count to (CPU_cores - 2) by default.

4. HERMETIC ENVIRONMENT CONFIGURATION:
   Child worker processes run with an isolated environment dictionary setting
   ROOTSYS, SARTRE_DIR, PYTHIA8, and dynamic library loader search paths
   (LD_LIBRARY_PATH), ensuring failure-free execution regardless of how the
   outer terminal was launched.

5. AUTOMATED ROOT TREE MERGING (`hadd`):
   When all worker chunks successfully complete, the orchestrator invokes CERN
   ROOT's `hadd -f` tool. This automatically concatenates the individual TTree
   instances and properly accumulates the cross-section summary histogram into
   a single consolidated dataset (e.g., data/sartre_bSat_HMPZ_100k.root).

6. BENCHMARK & METRIC PERSISTENCE:
   Stores execution runtimes, cross sections, and file sizes to a structured
   JSON catalog (`data/cross_sections.json`).
================================================================================
"""

import os
import sys
import time
import json
import shutil
import argparse
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_BIN = PROJECT_ROOT / "simulation" / "sartre_pp_jpsi"
DATA_DIR = PROJECT_ROOT / "data"
CHUNKS_DIR = DATA_DIR / "chunks"

def get_hermetic_env():
    """
    Construct an isolated execution environment dictionary with all required
    paths for CERN ROOT, Sartre 2, and Pythia 8.
    """
    env = os.environ.copy()
    root_dir = str(PROJECT_ROOT / "root_install")
    sartre_dir = str(PROJECT_ROOT / "sartre_install" / "sartre")
    pythia_dir = str(PROJECT_ROOT / "pythia8_install")

    env["ROOTSYS"] = root_dir
    env["SARTRE_DIR"] = sartre_dir
    env["PYTHIA8"] = pythia_dir
    env["PYTHIA8DATA"] = f"{pythia_dir}/share/Pythia8/xmldoc"

    # Prepend local compiled library directories to LD_LIBRARY_PATH
    orig_ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{root_dir}/lib:{sartre_dir}/lib:{pythia_dir}/lib:{orig_ld}"

    # Prepend binaries to PATH
    orig_path = env.get("PATH", "")
    env["PATH"] = f"{root_dir}/bin:{sartre_dir}/bin:{pythia_dir}/bin:{orig_path}"
    return env

def run_worker_chunk(worker_id, runcard_path, chunk_file, n_events, seed, known_cs):
    """
    Execute a single Sartre C++ simulation driver instance in an isolated subprocess.

    Parameters:
      worker_id:    Sequential integer identifier (1, 2, ..., N)
      runcard_path: Path to the Sartre runcard configuration file
      chunk_file:   Path where the output chunk ROOT file will be written
      n_events:     Number of events for this specific worker chunk
      seed:         Unique random seed for this worker chunk
      known_cs:     Precomputed cross section in nb (or None)

    Returns:
      (success, worker_id, elapsed_time, chunk_file, error_message)
    """
    if not SIM_BIN.exists():
        return False, worker_id, 0.0, chunk_file, f"Driver binary not found: {SIM_BIN}. Compile it first!"

    cmd = [
        str(SIM_BIN),
        str(runcard_path),
        str(chunk_file),
        str(n_events),
        str(seed)
    ]
    if known_cs is not None and known_cs > 0:
        cmd.append(str(known_cs))

    start_time = time.time()
    env = get_hermetic_env()

    # Launch subprocess with nice -n 10 priority to prevent core starvation
    nice_cmd = ["nice", "-n", "10"] + cmd
    res = subprocess.run(
        nice_cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env
    )
    elapsed = time.time() - start_time

    if res.returncode != 0:
        print(f"[Worker {worker_id:02d}] FAILED with returncode {res.returncode}")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        return False, worker_id, elapsed, chunk_file, res.stderr or res.stdout

    return True, worker_id, elapsed, chunk_file, ""

def generate_model_parallel(model_name, runcard_rel, total_events, num_workers, base_seed, known_cs=None):
    """
    Distribute event generation for a physics model across multiple worker processes,
    wait for all chunks to finish, and merge chunk files into the final ROOT dataset.
    """
    print(f"\n{'='*70}")
    print(f"  Starting Multi-Core Parallel Simulation: {model_name}")
    print(f"  Total Requested Events: {total_events:,}")
    print(f"  Allocated Worker Cores: {num_workers}")
    print(f"  Base Random Seed:       {base_seed}")
    if known_cs:
        print(f"  Target Cross Section:   {known_cs} nb")
    print(f"{'='*70}")

    runcard_path = PROJECT_ROOT / runcard_rel
    if not runcard_path.exists():
        raise FileNotFoundError(f"Runcard not found: {runcard_path}")

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # Calculate event partitioning
    events_per_worker = total_events // num_workers
    remainder = total_events % num_workers

    worker_tasks = []
    chunk_files = []

    for i in range(num_workers):
        # Distribute any remaining events across initial workers
        chunk_events = events_per_worker + (1 if i < remainder else 0)
        chunk_file = CHUNKS_DIR / f"chunk_{model_name}_worker_{i+1:02d}.root"
        # Disjoint deterministic seed
        chunk_seed = base_seed + 100 * (i + 1)

        chunk_files.append(chunk_file)
        worker_tasks.append((i + 1, runcard_path, chunk_file, chunk_events, chunk_seed, known_cs))

    t0 = time.time()
    completed = 0

    # Execute workers concurrently across CPU cores
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(run_worker_chunk, *task): task[0]
            for task in worker_tasks
        }
        for future in as_completed(futures):
            worker_id = futures[future]
            success, w_id, elapsed, c_file, err = future.result()
            if success:
                completed += 1
                pct = 100.0 * completed / num_workers
                print(f"  -> Worker {w_id:02d}/{num_workers:02d} completed in {elapsed:.1f}s ({pct:.0f}% finished)")
            else:
                print(f"  -> Worker {w_id:02d} FAILED: {err}")
                raise RuntimeError(f"Parallel worker {w_id} encountered a fatal error!")

    total_time = time.time() - t0
    print(f"\nAll {num_workers} parallel workers finished in {total_time:.1f} seconds ({total_time/60.0:.2f} min).")

    # Merge individual chunk files into consolidated dataset
    final_root_file = DATA_DIR / f"sartre_{model_name}_100k.root"
    print(f"Merging {len(chunk_files)} chunk files into {final_root_file} via ROOT hadd...")

    env = get_hermetic_env()
    hadd_cmd = ["hadd", "-f", str(final_root_file)] + [str(f) for f in chunk_files]
    hadd_res = subprocess.run(hadd_cmd, capture_output=True, text=True, env=env)
    if hadd_res.returncode != 0:
        print("hadd error output:", hadd_res.stderr)
        raise RuntimeError("CERN ROOT hadd failed to merge chunk files!")

    print(f"Merge successful: {final_root_file} ({final_root_file.stat().st_size / 1e6:.1f} MB)")

    # Provide short convenience symlink (e.g., sartre_bSat_100k.root -> sartre_bSat_HMPZ_100k.root)
    short_name = model_name.split("_")[0]
    symlink_file = DATA_DIR / f"sartre_{short_name}_100k.root"
    if symlink_file.exists() or symlink_file.is_symlink():
        symlink_file.unlink()
    try:
        symlink_file.symlink_to(final_root_file.name)
        print(f"Created convenience symlink: {symlink_file.name} -> {final_root_file.name}")
    except Exception as e:
        shutil.copy2(final_root_file, symlink_file)

    # Clean up temporary chunk files to conserve disk space
    for cf in chunk_files:
        if cf.exists():
            cf.unlink()

    return final_root_file, total_time

def main():
    parser = argparse.ArgumentParser(
        description="Run multi-core parallel event generation for Sartre 2 UPC simulation."
    )
    parser.add_argument(
        "--events",
        type=int,
        default=100000,
        help="Total events to generate per model (default: 100,000)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Number of parallel worker processes (default: 12)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="all",
        choices=["all", "bSat", "bNonSat", "STU"],
        help="Dipole saturation model to simulate (default: all)"
    )
    args = parser.parse_args()

    # Automatic safety check on available CPU threads
    available_cores = os.cpu_count() or 1
    safe_workers = min(args.workers, max(1, available_cores - 2))
    print(f"Detected {available_cores} CPU cores. Running with {safe_workers} parallel workers.")

    cs_dict = {}
    cs_file = DATA_DIR / "cross_sections.json"
    if cs_file.exists():
        with open(cs_file, "r") as f:
            try:
                cs_dict = json.load(f)
            except Exception:
                cs_dict = {}

    # 1. bSat (IPsat gluon saturation) with HMPZ parameter set
    if args.model in ["all", "bSat"]:
        f_bSat, t_bSat = generate_model_parallel(
            model_name="bSat_HMPZ",
            runcard_rel="simulation/runcard_bSat_HMPZ.txt",
            total_events=args.events,
            num_workers=safe_workers,
            base_seed=20261025,
            known_cs=35.1315
        )
        cs_dict["bSat_HMPZ"] = {
            "total_cross_section_nb": 35.1315,
            "total_cross_section_ee_pb": 35.1315 * 1000.0 * 0.05971,  # BR(J/psi -> e+e-) = 5.971%
            "events_generated": args.events,
            "wall_clock_seconds": round(t_bSat, 2),
            "output_file": str(f_bSat.name)
        }

    # 2. bNonSat (linear DGLAP evolution without saturation) with HMPZ parameter set
    if args.model in ["all", "bNonSat"]:
        f_bNonSat, t_bNonSat = generate_model_parallel(
            model_name="bNonSat_HMPZ",
            runcard_rel="simulation/runcard_bNonSat_HMPZ.txt",
            total_events=args.events,
            num_workers=safe_workers,
            base_seed=20261026,
            known_cs=39.2815
        )
        cs_dict["bNonSat_HMPZ"] = {
            "total_cross_section_nb": 39.2815,
            "total_cross_section_ee_pb": 39.2815 * 1000.0 * 0.05971,  # BR(J/psi -> e+e-) = 5.971%
            "events_generated": args.events,
            "wall_clock_seconds": round(t_bNonSat, 2),
            "output_file": str(f_bNonSat.name)
        }

    # Persist summary metrics to data/cross_sections.json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(cs_file, "w") as f:
        json.dump(cs_dict, f, indent=2)
    print(f"\nPersisted cross-section and runtime metrics to: {cs_file}")

if __name__ == "__main__":
    main()

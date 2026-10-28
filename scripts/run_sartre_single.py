#!/usr/bin/env python3
"""
================================================================================
run_sartre_single.py

Minimalist Single-Instance Sartre 2 Simulation Runner
Analysis of J/psi Photoproduction in p+p Collisions at sqrt(s) = 510 GeV
Author: Štěpán Skalka (CTU in Prague)

================================================================================
PURPOSE & USAGE:
================================================================================
This script is a minimalist, easy-to-read Python driver that executes a single
instance of the Sartre C++ simulation binary (`simulation/sartre_pp_jpsi`).

It is ideal for:
  - Quick physics verification and test runs (e.g. 500 or 1,000 events)
  - Testing custom runcards and parameters
  - Single-core production without multiprocessing overhead

Usage Examples:
  # 1. Run with default parameters (1,000 events with bSat):
  python3 scripts/run_sartre_single.py

  # 2. Run a specific runcard and output file:
  python3 scripts/run_sartre_single.py \
      --runcard simulation/runcard_bSat_HMPZ.txt \
      --output data/test_bSat_1k.root \
      --events 1000 \
      --seed 20261025
================================================================================
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

# Identify repository directory structure relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_BIN = PROJECT_ROOT / "simulation" / "sartre_pp_jpsi"
DEFAULT_RUNCARD = PROJECT_ROOT / "simulation" / "runcard_bSat_HMPZ.txt"
DATA_DIR = PROJECT_ROOT / "data"

def setup_environment():
    """
    Construct an environment dictionary with all necessary library search paths
    and binary search paths for CERN ROOT, Sartre 2, and Pythia 8.
    """
    env = os.environ.copy()
    root_dir = str(PROJECT_ROOT / "root_install")
    sartre_dir = str(PROJECT_ROOT / "sartre_install" / "sartre")
    pythia_dir = str(PROJECT_ROOT / "pythia8_install")

    env["ROOTSYS"] = root_dir
    env["SARTRE_DIR"] = sartre_dir
    env["PYTHIA8"] = pythia_dir
    env["PYTHIA8DATA"] = f"{pythia_dir}/share/Pythia8/xmldoc"

    # Prepend shared libraries so the Linux dynamic loader (ld.so) resolves them
    orig_ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{root_dir}/lib:{sartre_dir}/lib:{pythia_dir}/lib:{orig_ld}"

    # Prepend binary paths
    orig_path = env.get("PATH", "")
    env["PATH"] = f"{root_dir}/bin:{sartre_dir}/bin:{pythia_dir}/bin:{orig_path}"
    return env

def run_simulation(runcard_path, output_path, n_events, seed, cross_section=None):
    """
    Execute the simulation driver binary with the specified arguments.
    """
    if not SIM_BIN.exists():
        print(f"ERROR: Simulation binary not found at: {SIM_BIN}")
        print("Please compile the driver first using the compilation command in README.md.")
        sys.exit(1)

    runcard_file = Path(runcard_path)
    if not runcard_file.exists():
        print(f"ERROR: Runcard file not found at: {runcard_file}")
        sys.exit(1)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Construct positional arguments expected by sartre_pp_jpsi:
    #   sartre_pp_jpsi <runcard.txt> [output.root] [nEvents] [seed] [known_cs_nb]
    cmd = [
        str(SIM_BIN),
        str(runcard_file),
        str(output_file),
        str(n_events),
        str(seed)
    ]
    if cross_section is not None and cross_section > 0:
        cmd.append(str(cross_section))

    print(f"{'='*60}")
    print(f"  Starting Sartre Single Simulation")
    print(f"  Runcard:     {runcard_file}")
    print(f"  Output ROOT: {output_file}")
    print(f"  Events:      {n_events:,}")
    print(f"  Random Seed: {seed}")
    if cross_section:
        print(f"  Cross Sec:   {cross_section} nb")
    print(f"{'='*60}\n")

    start_time = time.time()
    env = setup_environment()

    # Execute driver process and stream output to terminal
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    elapsed = time.time() - start_time

    if proc.returncode != 0:
        print(f"\nSimulation process exited with ERROR code {proc.returncode}!")
        sys.exit(proc.returncode)

    file_size_mb = output_file.stat().st_size / (1024 * 1024) if output_file.exists() else 0.0
    print(f"\n{'='*60}")
    print(f"  Simulation completed successfully in {elapsed:.2f} seconds.")
    print(f"  Output file: {output_file} ({file_size_mb:.2f} MB)")
    print(f"{'='*60}")

def main():
    parser = argparse.ArgumentParser(
        description="Run a single-instance Sartre 2 simulation with custom events and seeds."
    )
    parser.add_argument(
        "--runcard",
        type=str,
        default=str(DEFAULT_RUNCARD),
        help="Path to Sartre runcard configuration file (default: simulation/runcard_bSat_HMPZ.txt)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DATA_DIR / "test_single_output.root"),
        help="Target output ROOT file path (default: data/test_single_output.root)"
    )
    parser.add_argument(
        "--events",
        type=int,
        default=1000,
        help="Number of events to generate (default: 1,000)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261025,
        help="Pseudo-random generator seed (default: 20261025)"
    )
    parser.add_argument(
        "--cs",
        type=float,
        default=None,
        help="Known total cross section in nb to bypass runtime table integration (optional)"
    )

    args = parser.parse_args()
    run_simulation(
        runcard_path=args.runcard,
        output_path=args.output,
        n_events=args.events,
        seed=args.seed,
        cross_section=args.cs
    )

if __name__ == "__main__":
    main()

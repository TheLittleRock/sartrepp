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
import queue
import threading
import argparse
import subprocess
from pathlib import Path

# Identify repository directory structure relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_BIN = PROJECT_ROOT / "simulation" / "sartre_pp_jpsi"
DEFAULT_RUNCARD = PROJECT_ROOT / "simulation" / "runcard_bSat_HMPZ.txt"
DATA_DIR = PROJECT_ROOT / "data"

def print_progress_bar(current, total, start_time, bar_length=30):
    """
    Displays an in-place, single-line progress bar:
      [===================>       ]  75.0% (75,000/100,000) | 450 ev/s | Elapsed: 2m 45s | ETA: 55s
    """
    fraction = min(1.0, current / total) if total > 0 else 0.0
    percent = fraction * 100
    filled = int(bar_length * fraction)
    bar = "=" * (filled - 1) + ">" if 0 < filled < bar_length else "=" * filled
    bar = bar.ljust(bar_length, " ")

    elapsed = time.time() - start_time
    rate = current / elapsed if elapsed > 0.5 else 0.0
    eta_sec = (total - current) / rate if rate > 0 else 0.0

    def format_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        elif m > 0:
            return f"{m}m {s:02d}s"
        else:
            return f"{s}s"

    elapsed_str = format_time(elapsed)
    eta_str = format_time(eta_sec) if fraction < 1.0 else "0s"

    status = f"\r[{bar}] {percent:5.1f}% ({current:,}/{total:,}) | {rate:4.0f} ev/s | Elapsed: {elapsed_str} | ETA: {eta_str}"
    sys.stdout.write(status)
    sys.stdout.flush()

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
        print(f"  Cross Sec:   {cross_section} nb (precomputed)")
    else:
        print(f"  Cross Sec:   Will be calculated dynamically via Sartre phase space integration")
    print(f"{'='*60}\n")

    start_time = time.time()
    env = setup_environment()

    # Launch driver process and stream stdout to display progress in real time
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    output_queue = queue.Queue()

    def stream_reader(pipe):
        for line in iter(pipe.readline, ''):
            output_queue.put(line)
        pipe.close()

    reader_thread = threading.Thread(target=stream_reader, args=(proc.stdout,), daemon=True)
    reader_thread.start()

    started_events = False
    event_start_time = time.time()
    integrating_cs = False
    cs_start_time = None
    spinner = ["|", "/", "-", "\\"]
    spin_idx = 0

    while proc.poll() is None or not output_queue.empty():
        try:
            line = output_queue.get(timeout=0.25)
            if line.startswith("Processed "):
                if not started_events:
                    started_events = True
                    event_start_time = time.time()
                try:
                    # Format: "Processed 100 / 1000 events..."
                    current = int(line.split()[1])
                    print_progress_bar(current, n_events, event_start_time)
                    if current >= n_events:
                        print()  # Finalize bar on the last event
                except (IndexError, ValueError):
                    pass
            elif "Calculating total cross section" in line:
                integrating_cs = True
                cs_start_time = time.time()
                sys.stdout.write(line)
                sys.stdout.flush()
            elif line.startswith("Finished!"):
                if integrating_cs:
                    sys.stdout.write("\r" + " " * 85 + "\r")  # Clear active indicator line
                    integrating_cs = False
                sys.stdout.write(line)
                sys.stdout.flush()
            else:
                sys.stdout.write(line)
                sys.stdout.flush()
        except queue.Empty:
            if integrating_cs and cs_start_time is not None:
                elapsed_cs = time.time() - cs_start_time
                m, s = divmod(int(elapsed_cs), 60)
                time_str = f"{m}m {s:02d}s" if m > 0 else f"{s}s"
                char = spinner[spin_idx % len(spinner)]
                spin_idx += 1
                sys.stdout.write(f"\r  [{char}] Phase-space integration in progress... (Elapsed: {time_str})")
                sys.stdout.flush()

    if integrating_cs:
        sys.stdout.write("\r" + " " * 85 + "\r")
        sys.stdout.flush()

    proc.wait()
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

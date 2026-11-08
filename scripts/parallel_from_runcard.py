#!/usr/bin/env python3
"""
Parallel Runner for Sartre 2 (sartre_pp_jpsi)
=============================================
Splits a Sartre simulation from a single runcard across multiple CPU cores,
runs the C++ binary on each core with a unique random seed, and merges
the output ROOT files using `hadd`.

Requires your `.venv` to be activated (`source .venv/bin/activate`).
"""

import os
import sys
import glob
import time
import argparse
import readline
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# --- Folder and Binary Paths ---
# PROJECT_ROOT is the main project directory (one level up from this script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_BIN      = PROJECT_ROOT / "simulation" / "sartre_pp_jpsi"
CHUNKS_DIR   = PROJECT_ROOT / "data" / "chunks"


def ask_for_runcard():
    """
    If no runcard was given on the command line, ask the user to type the path
    interactively. Uses `readline` so pressing Tab autocompletes file names.
    """
    def tab_completer(text, state):
        # Find all files/folders starting with what the user typed
        matches = glob.glob(os.path.expanduser(text) + "*")
        # Add '/' to folders so pressing Tab continues inside the folder
        matches = [m + "/" if os.path.isdir(m) else m for m in matches]
        return matches[state] if state < len(matches) else None

    # Enable Tab key completion in the terminal prompt
    readline.set_completer_delims(" \t\n;")
    readline.parse_and_bind("tab: complete")
    readline.set_completer(tab_completer)

    while True:
        user_input = input("Enter path to runcard (Tab to autocomplete): ").strip()
        if not user_input:
            continue

        # Check if the path exists relative to current folder OR project root
        path = Path(user_input).expanduser()
        if not path.is_file() and (PROJECT_ROOT / path).is_file():
            path = PROJECT_ROOT / path

        if path.is_file():
            return path.resolve()
        print(f"File not found: '{user_input}'. Try again.")


def read_runcard_settings(runcard_path):
    """
    Read default settings (`numberOfEvents`, `rootfile`, `seed`) directly
    from the runcard text file so we don't have to pass them manually.
    """
    events   = 100000
    rootfile = PROJECT_ROOT / "data" / f"{runcard_path.stem}.root"
    seed     = 20261025

    with open(runcard_path, "r") as f:
        for line in f:
            # Ignore comments (everything after '#')
            clean = line.split("#")[0].strip()
            if "=" not in clean:
                continue

            # Split `key = value`
            key, value = [part.strip() for part in clean.split("=", 1)]
            if key == "numberOfEvents":
                events = int(value)
            elif key == "rootfile":
                rootfile = PROJECT_ROOT / value
            elif key == "seed":
                seed = int(value)

    return events, rootfile.resolve(), seed


def run_single_worker(task):
    """
    Runs one instance of the C++ simulation (`sartre_pp_jpsi`) on a single CPU core.
    Each worker writes its own temporary ROOT file (`chunk_file`).
    """
    worker_id, runcard, chunk_file, n_events, seed, known_cs = task

    # Build the command matching sartre_pp_jpsi.cxx arguments:
    # ./sartre_pp_jpsi <runcard> <output.root> <nEvents> <seed> [known_cs_nb]
    # `nice -n 10` lowers CPU priority slightly so your PC doesn't freeze up.
    cmd = [
        "nice", "-n", "10",
        str(SIM_BIN),
        str(runcard),
        str(chunk_file),
        str(n_events),
        str(seed),
    ]
    # If known_cs is provided, pass it as 5th argument to skip end-of-run integration
    if known_cs is not None and known_cs > 0:
        cmd.append(str(known_cs))

    start = time.time()
    # Run the C++ program. capture_output=True prevents 12 workers from printing at once.
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    elapsed = time.time() - start

    # If the C++ program failed (returncode != 0), stop and print its error output
    if result.returncode != 0:
        raise RuntimeError(f"Worker {worker_id} crashed!\n{result.stderr or result.stdout}")

    print(f"  -> Worker {worker_id:02d} finished {n_events} events in {elapsed:.1f}s")
    return chunk_file


def main():
    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Run Sartre 2 simulation in parallel.")
    parser.add_argument("runcard", nargs="?", help="Path to runcard (prompts if omitted)")
    parser.add_argument("-w", "--workers", type=int, default=12, help="Number of CPU cores (default: 12)")
    parser.add_argument("-e", "--events", type=int, help="Override total events from runcard")
    parser.add_argument("-o", "--output", type=Path, help="Override output ROOT file from runcard")
    parser.add_argument("--cs", type=float, help="Known cross-section in nb (optional)")
    args = parser.parse_args()

    # 1. Check that the compiled C++ binary exists
    if not SIM_BIN.is_file():
        sys.exit(f"Error: C++ binary not found at {SIM_BIN}. Compile it first.")

    # 2. Get the runcard path (from command line argument OR interactive prompt)
    if args.runcard:
        runcard_path = Path(args.runcard).expanduser()
        if not runcard_path.is_file() and (PROJECT_ROOT / runcard_path).is_file():
            runcard_path = PROJECT_ROOT / runcard_path
        if not runcard_path.is_file():
            sys.exit(f"Error: Runcard not found at '{args.runcard}'")
        runcard_path = runcard_path.resolve()
    else:
        runcard_path = ask_for_runcard()

    # 3. Read settings from the runcard (unless overridden by command-line flags)
    rc_events, rc_output, base_seed = read_runcard_settings(runcard_path)
    total_events = args.events if args.events else rc_events
    output_file  = args.output.resolve() if args.output else rc_output

    # 4. Cap the number of workers to (Total CPU Cores - 2) so the PC stays usable
    total_cores = os.cpu_count() or 1
    num_workers = min(args.workers, max(1, total_cores - 2))

    print("=" * 60)
    print(f"Runcard:      {runcard_path.name}")
    print(f"Total Events: {total_events:,} (across {num_workers} CPU cores)")
    print(f"Output File:  {output_file}")
    print("=" * 60)

    # Make sure output folders exist
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 5. Split total events across the workers
    # Example: 100,000 // 12 = 8,333 events per worker, with 4 leftover events
    base_events = total_events // num_workers
    remainder   = total_events % num_workers

    tasks = []
    for i in range(num_workers):
        worker_id    = i + 1
        # Distribute the leftover remainder events (1 extra event to the first few workers)
        chunk_events = base_events + (1 if i < remainder else 0)

        # CRITICAL FOR MONTE CARLO: Give every worker a different random seed!
        # Otherwise all cores would simulate the exact same collisions.
        worker_seed = base_seed + (100 * worker_id)

        # Path for this worker's temporary ROOT file
        chunk_file = CHUNKS_DIR / f"chunk_{runcard_path.stem}_{worker_id:02d}.root"
        tasks.append((worker_id, runcard_path, chunk_file, chunk_events, worker_seed, args.cs))

    # 6. Launch all workers in parallel
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Runs `run_single_worker` for each item in `tasks` across separate CPU cores
        chunk_files = list(executor.map(run_single_worker, tasks))

    print(f"\nAll workers finished in {time.time() - t0:.1f}s. Merging files with hadd...")

    # 7. Merge all temporary chunk files into the final ROOT file using ROOT's `hadd -f`
    hadd_cmd = ["hadd", "-f", str(output_file)] + [str(f) for f in chunk_files]
    hadd_res = subprocess.run(hadd_cmd, capture_output=True, text=True)
    if hadd_res.returncode != 0:
        sys.exit(f"hadd failed:\n{hadd_res.stderr}")

    # 8. Delete the temporary chunk files
    for cf in chunk_files:
        cf.unlink(missing_ok=True)

    print(f"Done! Final ROOT file saved to: {output_file}")


if __name__ == "__main__":
    main()
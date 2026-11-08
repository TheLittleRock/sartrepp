#!/usr/bin/env python3
"""
Parallel Runner for Sartre 2 (sartre_pp_jpsi)
=============================================
Splits a Sartre simulation from a single runcard across multiple CPU cores,
runs the C++ binary on each core with a unique random seed, displays a live
progress bar, and merges the output ROOT files using `hadd`.

Requires your `.venv` to be activated (`source .venv/bin/activate`).
"""

import os
import sys
import glob
import time
import queue
import threading
import argparse
import readline
import subprocess
from pathlib import Path

# --- Folder and Binary Paths ---
# PROJECT_ROOT is the main project directory (one level up from this script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_BIN      = PROJECT_ROOT / "simulation" / "sartre_pp_jpsi"
CHUNKS_DIR   = PROJECT_ROOT / "data" / "chunks"


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


def ask_for_runcard():
    """
    If no runcard was given on the command line, ask the user to type the path
    interactively. Uses `readline` so pressing Tab autocompletes file names.
    """
    def tab_completer(text, state):
        matches = glob.glob(os.path.expanduser(text) + "*")
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
            clean = line.split("#")[0].strip()
            if "=" not in clean:
                continue

            key, value = [part.strip() for part in clean.split("=", 1)]
            if key == "numberOfEvents":
                events = int(value)
            elif key == "rootfile":
                rootfile = PROJECT_ROOT / value
            elif key == "seed":
                seed = int(value)

    return events, rootfile.resolve(), seed


def main():
    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Run Sartre 2 simulation in parallel with live progress.")
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
    if args.cs:
        print(f"Cross Sec:    {args.cs} nb (precomputed)")
    else:
        print(f"Cross Sec:    Will be calculated dynamically via Sartre phase-space integration")
    print("=" * 60)

    # Make sure output folders exist
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 5. Split total events across the workers
    base_events = total_events // num_workers
    remainder   = total_events % num_workers

    tasks = []
    for i in range(num_workers):
        worker_id    = i + 1
        chunk_events = base_events + (1 if i < remainder else 0)
        worker_seed  = base_seed + (100 * worker_id)
        chunk_file   = CHUNKS_DIR / f"chunk_{runcard_path.stem}_{worker_id:02d}.root"
        tasks.append((worker_id, runcard_path, chunk_file, chunk_events, worker_seed, args.cs))

    # 6. Launch all workers in parallel
    print(f"\nLaunching {num_workers} parallel workers...")
    progress_queue = queue.Queue()

    def stream_worker_output(proc, wid, stderr_lines):
        """Reads stdout from worker process and forwards progress lines to the queue."""
        for line in proc.stdout:
            if line.startswith("Processed "):
                try:
                    done = int(line.split()[1])
                    progress_queue.put((wid, done))
                except (IndexError, ValueError):
                    pass
        for err_line in proc.stderr:
            stderr_lines.append(err_line)

    procs = []
    worker_stderrs = {}
    chunk_files = []

    for worker_id, runcard, chunk_file, chunk_events, worker_seed, cs in tasks:
        cmd = [
            "nice", "-n", "10",
            str(SIM_BIN),
            str(runcard),
            str(chunk_file),
            str(chunk_events),
            str(worker_seed),
        ]
        if cs is not None and cs > 0:
            cmd.append(str(cs))

        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        stderr_lines = []
        worker_stderrs[worker_id] = stderr_lines

        t = threading.Thread(
            target=stream_worker_output,
            args=(proc, worker_id, stderr_lines),
            daemon=True
        )
        t.start()
        procs.append((worker_id, proc, chunk_events))
        chunk_files.append(chunk_file)

    # Track progress and update live in-place progress bar
    worker_progress = {w_id: 0 for w_id, _, _ in procs}
    t0 = time.time()
    print_progress_bar(0, total_events, t0)

    # Phase 1: Monitor event generation progress
    while any(p.poll() is None for _, p, _ in procs):
        while True:
            try:
                wid, done = progress_queue.get_nowait()
                worker_progress[wid] = done
            except queue.Empty:
                break

        total_done = sum(worker_progress.values())
        print_progress_bar(total_done, total_events, t0)
        if total_done >= total_events:
            break
        time.sleep(0.1)

    # Empty any final progress messages
    while not progress_queue.empty():
        try:
            wid, done = progress_queue.get_nowait()
            worker_progress[wid] = done
        except queue.Empty:
            break

    # Print final 100% progress bar
    print_progress_bar(total_events, total_events, t0)
    print()  # Final newline for progress bar

    # Phase 2: If workers are still running (calculating phase space integration), show live spinner
    spinner = ["|", "/", "-", "\\"]
    spin_idx = 0
    wait_start = time.time()
    while any(p.poll() is None for _, p, _ in procs):
        elapsed_w = time.time() - wait_start
        m, s = divmod(int(elapsed_w), 60)
        time_str = f"{m}m {s:02d}s" if m > 0 else f"{s}s"
        char = spinner[spin_idx % len(spinner)]
        spin_idx += 1
        active_count = sum(1 for _, p, _ in procs if p.poll() is None)
        sys.stdout.write(f"\r  [{char}] Events complete. Waiting for {active_count} worker(s) to finish phase-space integration... (Elapsed: {time_str})")
        sys.stdout.flush()
        time.sleep(0.5)

    sys.stdout.write("\r" + " " * 95 + "\r")
    sys.stdout.flush()

    # Check for errors in any worker
    failed = False
    for worker_id, proc, _ in procs:
        proc.wait()
        if proc.returncode != 0:
            err_msg = "".join(worker_stderrs[worker_id])
            print(f"ERROR: Worker {worker_id:02d} crashed with exit code {proc.returncode}!\n{err_msg}")
            failed = True

    if failed:
        sys.exit(1)

    print(f"\nAll {num_workers} workers finished in {time.time() - t0:.1f}s. Merging files with hadd...")

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

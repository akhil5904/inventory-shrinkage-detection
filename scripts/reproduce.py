#!/usr/bin/env python
"""
Reproducibility test — runs the generator twice with the same seed and
compares row counts and CSV checksums to prove deterministic output.

Usage:
  python scripts/reproduce.py              # full scale
  python scripts/reproduce.py --scale 0.01 # fast smoke test
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generator import config
from generator.main import run


def checksum_dir(csv_dir: Path) -> dict:
    sums = {}
    for f in sorted(csv_dir.glob("*.csv")):
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        sums[f.name] = h
    return sums


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=0.01,
                        help="Scale factor (default 0.01 for speed)")
    args = parser.parse_args()

    base     = config.BASE_DIR
    run1_dir = base / "data_run1"
    run2_dir = base / "data_run2"

    for d in (run1_dir, run2_dir):
        if d.exists():
            shutil.rmtree(d)

    # ── Run 1 ──────────────────────────────────────────────────
    print("=" * 60)
    print(f"Run 1  (seed={config.SEED}, scale={args.scale})")
    print("=" * 60)
    config.DATA_DIR = run1_dir
    run(scale=args.scale)

    # ── Run 2 ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Run 2  (seed={config.SEED}, scale={args.scale})")
    print("=" * 60)
    config.DATA_DIR = run2_dir
    run(scale=args.scale)

    # ── Compare ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Comparing runs …")

    s1 = checksum_dir(run1_dir / "csv")
    s2 = checksum_dir(run2_dir / "csv")

    all_files = sorted(set(s1) | set(s2))
    mismatches = []
    for fname in all_files:
        h1 = s1.get(fname, "MISSING")
        h2 = s2.get(fname, "MISSING")
        match = h1 == h2
        icon  = "✓" if match else "✗"
        print(f"  {icon} {fname}")
        if not match:
            mismatches.append(fname)
            print(f"      run1: {h1}")
            print(f"      run2: {h2}")

    print()
    if mismatches:
        print(f"FAIL – {len(mismatches)} file(s) differ between runs.")
        sys.exit(1)
    else:
        print(f"PASS – all {len(all_files)} CSV files are byte-for-byte identical across both runs.")
        print(f"       Seed {config.SEED} is fully deterministic.")

    # Save report
    report = {
        "seed":         config.SEED,
        "scale":        args.scale,
        "files_checked":len(all_files),
        "mismatches":   mismatches,
        "result":       "PASS" if not mismatches else "FAIL",
    }
    report_path = base / "reproducibility_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport → {report_path}")

    # Clean up temp dirs
    shutil.rmtree(run1_dir)
    shutil.rmtree(run2_dir)


if __name__ == "__main__":
    main()

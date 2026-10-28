#!/usr/bin/env python
"""Entry point: generate synthetic inventory data.

Usage:
  python scripts/generate.py               # full scale (1M movements)
  python scripts/generate.py --scale 0.01  # starter dataset (~10k movements)
  python scripts/generate.py --scale 0.1   # medium dataset (~100k movements)
"""

import argparse
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from generator.main import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate inventory shrinkage synthetic data.")
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="Scale factor (0.01 = starter, 1.0 = full). Default: 1.0"
    )
    args = parser.parse_args()
    run(scale=args.scale)

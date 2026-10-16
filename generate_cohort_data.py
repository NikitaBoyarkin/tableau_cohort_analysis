"""Deterministic writer for ``cohort_data.csv`` (seed 42).

`cohort_data.csv` is a generated artifact (see ``.gitignore``): it is not stored
in git. This module is the committed writer that reproduces it byte-for-byte, so
a clean checkout can regenerate the file the claim gate reads.

    uv run python generate_cohort_data.py            # writes ./cohort_data.csv
    uv run python generate_cohort_data.py --out p.csv

Determinism: ``generate_data(DataConfig(seed=42))`` seeds a dedicated
``numpy.random.default_rng``, and the write is ``df.to_csv(index=False)`` with no
column reordering, so repeated runs produce identical bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib

from cohort_analysis import DataConfig, generate_data

DATA_PATH = pathlib.Path(__file__).parent / "cohort_data.csv"


def write_cohort_data(out: pathlib.Path = DATA_PATH) -> pathlib.Path:
    """Write the seeded synthetic dataset to ``out`` as CSV. Returns the path."""
    df = generate_data(DataConfig(seed=42))
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=DATA_PATH)
    args = parser.parse_args()

    path = write_cohort_data(args.out)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"wrote {path} ({path.stat().st_size} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Merge exported statistics sorted by suite, benchmark, and numeric core count."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parse_stats import FIELDS


def merge_summaries(directory):
    rows = []
    for source in sorted(directory.glob("*.json")):
        row = json.loads(source.read_text())["stats"]
        if row["variant"] != directory.name:
            raise ValueError(f"{source}: variant mismatch")
        rows.append(row)
    if not rows:
        raise ValueError(f"{directory}: no exported runs")
    rows.sort(key=lambda row: (row["suite"], row["benchmark"], int(row["cores"])))
    output = directory / "summary.csv"
    with NamedTemporaryFile(mode="w", dir=directory, newline="", encoding="utf-8",
                            delete=False) as temporary:
        path = Path(temporary.name)
        try:
            writer = csv.DictWriter(temporary, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            temporary.close()
            path.replace(output)
        finally:
            path.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant")
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", args.variant):
        parser.error("invalid variant name")
    try:
        print(merge_summaries(args.data / args.variant))
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"ERROR: {error}")

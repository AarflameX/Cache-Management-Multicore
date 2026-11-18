#!/usr/bin/env python3
"""Compare gem5 binary, seed, and simulator config across runs in a variant."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from run_provenance import VARIANT_FIELDS


def check_variant(directory):
    groups = {field: defaultdict(list) for field in VARIANT_FIELDS}
    runs = sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not runs:
        print(f"{directory}: no run directories")
        return False
    valid = True
    for run in runs:
        try:
            meta = json.loads((run / "run.json").read_text())
            if not isinstance(meta, dict):
                raise ValueError("run.json must contain an object")
        except (OSError, ValueError) as error:
            print(f"{run.name}: {error}")
            valid = False
            continue
        for field in VARIANT_FIELDS:
            value = meta.get(field)
            usable = (type(value) is int and 0 <= value < 2**32 if field == "seed"
                      else isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))
            if not usable:
                print(f"{run.name}: missing or invalid {field}")
                valid = False
            else:
                groups[field][value].append(run.name)
    for field, values in groups.items():
        if len(values) > 1:
            valid = False
            print(f"{field} differs:")
            for value, names in sorted(values.items(), key=lambda entry: (-len(entry[1]), entry[0])):
                print(f"  {value}: {', '.join(names)}")
    print(f"{directory}: {'consistent' if valid else 'inconsistent'} ({len(runs)} runs)")
    return valid


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant")
    parser.add_argument("--results", type=Path, default=Path("results"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", args.variant):
        parser.error("invalid variant name")
    try:
        sys.exit(0 if check_variant(args.results / args.variant) else 1)
    except OSError as error:
        sys.exit(f"ERROR: {error}")

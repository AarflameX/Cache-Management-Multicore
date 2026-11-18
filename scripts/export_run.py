#!/usr/bin/env python3
"""Export a finished run's metadata and parsed statistics to one JSON file."""
import argparse
from decimal import InvalidOperation
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parse_stats import parse_run


def export_run(run, data, dry_run=False):
    if not (run / "DONE").is_file() or (run / "FAILED").exists():
        raise ValueError(f"{run}: expected DONE and no FAILED marker")
    metadata = json.loads((run / "run.json").read_text())
    stats = parse_run(run)
    suite, bench, variant = (metadata[key] for key in ("suite", "benchmark", "variant"))
    for name in (suite, bench, variant):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name):
            raise ValueError(f"invalid output path component: {name!r}")
    target = data / variant / f"{suite}_{bench}_c{int(metadata['cores'])}.json"
    payload = json.dumps({"run": metadata, "stats": stats}, indent=2, sort_keys=True,
                         allow_nan=False) + "\n"
    if dry_run:
        print(f"Would write {target}")
        print(payload, end="")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        export_run(args.run, args.data, args.dry_run)
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        sys.exit(f"ERROR: {error}")

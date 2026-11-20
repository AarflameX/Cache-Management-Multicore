#!/usr/bin/env python3
"""Export a finished run's metadata and parsed statistics to one JSON file."""
import argparse
from decimal import InvalidOperation
import fcntl
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parse_stats import parse_run
from scripts.run_provenance import TREE_FIELDS


PROVENANCE_FIELDS = ("gem5_sha256", *TREE_FIELDS, "benchmark_sha256", "seed", "config_sha256",
                     "args", "extra_args", "roi", "guest")


def needs_write(target, payload, metadata, force):
    try:
        existing = target.read_bytes()
    except FileNotFoundError:
        return True
    if existing == payload:
        return False
    if force:
        return True
    try:
        previous = json.loads(existing)["run"]
        if not isinstance(previous, dict):
            raise ValueError("run metadata must be an object")
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError(f"{target}: cannot read existing provenance; use --force") from error
    missing = object()
    changed = [field for field in PROVENANCE_FIELDS
               if previous.get(field, missing) != metadata.get(field, missing)]
    if changed:
        raise ValueError(f"{target}: different provenance ({', '.join(changed)}); use --force")
    return True


def export_run(run, data, dry_run=False, force=False):
    if not (run / "DONE").is_file() or (run / "FAILED").exists():
        raise ValueError(f"{run}: expected DONE and no FAILED marker")
    metadata = json.loads((run / "run.json").read_text())
    stats = parse_run(run)
    suite, bench, variant = (metadata[key] for key in ("suite", "benchmark", "variant"))
    for name in (suite, bench, variant):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name):
            raise ValueError(f"invalid output path component: {name!r}")
    target = data / variant / f"{suite}_{bench}_c{int(metadata['cores'])}.json"
    payload = (json.dumps({"run": metadata, "stats": stats}, indent=2, sort_keys=True,
                          allow_nan=False) + "\n").encode("utf-8")
    if dry_run:
        if needs_write(target, payload, metadata, force):
            print(f"Would write {target}")
            print(payload.decode("utf-8"), end="")
        else:
            print(f"Unchanged {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    # Serialize the provenance check and replace across exporters in this directory.
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if not needs_write(target, payload, metadata, force):
            print(f"Unchanged {target}")
            return target
        with NamedTemporaryFile(dir=target.parent, prefix=".export-", delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(payload)
                output.close()
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        print(target)
    finally:
        os.close(directory)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="replace an export even if provenance differs")
    args = parser.parse_args()
    try:
        export_run(args.run, args.data, args.dry_run, args.force)
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        sys.exit(f"ERROR: {error}")

#!/usr/bin/env python3
"""Check provenance and baseline-v2 coverage in raw runs or exported JSONs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from run_provenance import TREE_FIELDS, VARIANT_FIELDS

TREE_HASH, _ = TREE_FIELDS
HASH_FIELDS = ("gem5_sha256", "config_sha256", "benchmark_sha256", TREE_HASH)
REQUIRED_OPTIONS = ("USE_X86_ISA", "RUBY_PROTOCOL_MESI_Two_Level")
V2_BENCHMARKS = {
    "gap": ("bfs", "pr"),
    "splash4": ("BARNES", "FFT", "LU-NOCONT", "OCEAN-CONT", "OCEAN-NOCONT", "RADIX"),
}


def report_build_differences(runner_options):
    if len(runner_options) < 2:
        return
    keys = {key for records in runner_options.values() for options in records for key in options}
    for key in sorted(keys):
        values = {runner: {options.get(key) for options in records}
                  for runner, records in runner_options.items()}
        if len({frozenset(options) for options in values.values()}) > 1:
            print(f"INFO: build option {key} differs:")
            for runner, options in sorted(values.items()):
                display = sorted("<missing>" if value is None else value for value in options)
                print(f"  {runner}: {', '.join(display)}")


def check_variant(directory, cores=(4,)):
    groups = defaultdict(lambda: defaultdict(list))
    runner_hashes = defaultdict(set)
    runner_options = defaultdict(list)
    exports = sorted(path for path in directory.glob("*.json") if path.is_file())
    if exports:
        sources = [(path, path, True) for path in exports]
    else:
        sources = [(run, run / "run.json",
                    (run / "DONE").is_file() and (run / "stats.txt").is_file()
                    and not (run / "FAILED").exists())
                   for run in sorted(directory.iterdir())
                   if run.is_dir() and not run.name.startswith(".") and run.name != "_failed"]
    valid = bool(sources)
    present = set()
    for entry, source, finished in sources:
        label = f"{entry.name} (runner unknown)"
        try:
            meta = json.loads(source.read_text())
            if exports:
                meta = meta["run"]
            if not isinstance(meta, dict):
                raise ValueError("run metadata must be an object")
            runner = meta.get("runner") or "unknown"
            if not isinstance(runner, str):
                raise ValueError("invalid runner name")
            label = f"{entry.name} (runner {runner})"
            suite, benchmark, count = (meta[key] for key in ("suite", "benchmark", "cores"))
            if (not isinstance(suite, str) or not isinstance(benchmark, str)
                    or type(count) is not int or count <= 0):
                raise ValueError("invalid suite, benchmark, or core count")
            if finished:
                present.add((suite, benchmark, count))
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(f"{label}: {error}")
            valid = False
            continue
        fields = (*VARIANT_FIELDS, "benchmark_sha256")
        if exports:
            commit = meta.get("gem5_git_commit", meta.get("gem5_commit"))
            groups["gem5_git_commit"][str(commit) if commit is not None else "null"].append(label)
            options = meta.get("gem5_build_options")
            if not isinstance(options, dict) or not all(isinstance(v, str) for v in options.values()):
                options = {}
            runner_options[runner].append(options)
            for option in REQUIRED_OPTIONS:
                if options.get(option) != "True":
                    print(f"{label}: expected {option} = True (found {options.get(option, 'missing')})")
                    valid = False
            fields += ("args", "extra_args")
            if TREE_HASH in meta:
                fields += (TREE_HASH,)
            else:
                print(f"INFO: {label}: missing {TREE_HASH}")
        for field in fields:
            value = meta.get(field)
            if field in HASH_FIELDS:
                usable = isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            elif field == "seed":
                usable = type(value) is int and 0 <= value < 2**32
            else:
                usable = isinstance(value, str) and (field in ("args", "extra_args") or value.strip())
            if not usable:
                print(f"{label}: missing or invalid {field}")
                valid = False
                continue
            group = field
            if field == "benchmark_sha256":
                group = f"{field} for {suite}/{benchmark}"
            elif field == "args":
                group = f"{field} for {suite}/{benchmark} c{count}"
                root = meta.get("repo_root")
                if isinstance(root, str) and root.startswith("/"):
                    value = value.replace(root.rstrip("/") + "/", "{repo}/")
            groups[group][value].append(label)
            if exports and field == "gem5_sha256":
                runner_hashes[runner].add(value)
    for field, values in sorted(groups.items()):
        if len(values) > 1:
            informational = (field == "gem5_git_commit"
                             or (bool(exports) and field == "gem5_sha256"
                                 and all(len(hashes) == 1 for hashes in runner_hashes.values())))
            if not informational:
                valid = False
            prefix = "INFO: " if informational else ""
            print(f"{prefix}{field} differs:")
            for value, names in sorted(values.items(), key=lambda entry: (-len(entry[1]), entry[0])):
                print(f"  {value}: {', '.join(names)}")
    report_build_differences(runner_options)
    print(f"{directory}: {'consistent' if valid else 'inconsistent'} ({len(sources)} runs)")
    expected = {(suite, benchmark, count) for suite, benchmarks in V2_BENCHMARKS.items()
                for benchmark in benchmarks for count in cores}
    missing = sorted(expected - present)
    print(f"Baseline-v2 coverage: {len(expected) - len(missing)}/{len(expected)}")
    for suite, benchmark, count in missing:
        print(f"  Missing: {suite}_{benchmark}_c{count}")
    return valid


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", help="variant name or path to a raw or exported variant directory")
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--cores", type=int, nargs="+", default=[4],
                        help="expected core counts for the coverage report (default: 4)")
    args = parser.parse_args()
    if any(core <= 0 or core % 2 for core in args.cores):
        parser.error("core counts must be positive even integers")
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", args.variant):
        directory = args.results / args.variant
    else:
        directory = Path(args.variant)
    try:
        sys.exit(0 if check_variant(directory, args.cores) else 1)
    except OSError as error:
        sys.exit(f"ERROR: {error}")

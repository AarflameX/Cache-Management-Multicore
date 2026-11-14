#!/usr/bin/env python3
"""Parse verified ROI dumps, never the automatic exit dump.

Names observed in a real GAP bfs -g 8 -n 1 --roi --cores 2 run:
  simSeconds
  board.cache_hierarchy.ruby_system.l1_controllers{core}.L1Dcache.m_demand_hits
  board.cache_hierarchy.ruby_system.l1_controllers{core}.L1Dcache.m_demand_misses
  board.cache_hierarchy.ruby_system.l2_controllers{bank}.L2cache.m_demand_hits
  board.cache_hierarchy.ruby_system.l2_controllers{bank}.L2cache.m_demand_misses
  board.processor.cores{core}.core.commitStats0.numInsts
  board.cache_hierarchy.ruby_system.l1_controllers{core}.prefetcher.RubyPrefetcher.numHits
  board.cache_hierarchy.ruby_system.l1_controllers{core}.prefetcher.RubyPrefetcher.numMissedPrefetchedBlocks
Instructions sum per-core committed instructions (not execute/fetch counts).
Optional prefetch columns use the L1 controller's RubyPrefetcher counters:
numHits counts first accesses to prefetched blocks; numMissedPrefetchedBlocks
counts misses on previously prefetched blocks, not all observed demand misses.
These are controller counters, not separately exposed L1Dcache counters.
Accesses are demand hits + demand misses. Controller/bank indices are discovered
in each selected ROI block; every selected block must have the same indices.
"""
import argparse
import csv
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

# benchmark: (number of ROI blocks, total blocks including automatic exit)
BLOCK_POLICY = {"VOLREND": (3, 4), "VOLREND-NPL": (3, 4)}
DEFAULT_POLICY = (1, 2)
PREFIX = "board.cache_hierarchy.ruby_system."
FIELDS = ["suite", "benchmark", "cores", "variant", "simSeconds",
          "L1D_hits", "L1D_misses", "L1D_accesses", "L1D_miss_rate",
          "L2_hits", "L2_misses", "L2_accesses", "L2_miss_rate",
          "L1D_imbalance", "instructions", "L1D_MPKI", "L2_MPKI",
          "L1D_prefetch_hits", "L1D_prefetch_misses", "wall_seconds"]
FIELDS += [f"core{i}_L1D_{field}" for i in range(8)
           for field in ("accesses", "miss_rate")]


def parse_run(run):
    meta = json.loads((run / "run.json").read_text())
    blocks, current = [], None
    for line in (run / "stats.txt").read_text().splitlines():
        if "Begin Simulation Statistics" in line:
            if current is not None:
                raise ValueError("nested statistics block")
            current = {}
        elif "End Simulation Statistics" in line:
            if current is None:
                raise ValueError("unmatched statistics block end")
            blocks.append(current)
            current = None
        elif current is not None:
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                current[parts[0]] = parts[1]
    if current is not None:
        raise ValueError("incomplete statistics block")
    roi_enabled = meta.get("roi", 1)
    if type(roi_enabled) not in (bool, int) or roi_enabled not in (0, 1):
        raise ValueError("run.json roi must be a bool or integer 0/1")
    cores = int(meta["cores"])
    if cores <= 0:
        raise ValueError("run.json cores must be positive")
    roi, expected = (BLOCK_POLICY.get(meta["benchmark"].upper(), DEFAULT_POLICY)
                     if roi_enabled else (1, 1))
    if len(blocks) != expected:
        raise ValueError(f"expected {expected} statistics blocks, found {len(blocks)}")

    def indices(block, controller):
        pattern = re.compile(re.escape(PREFIX) + controller + r"(\d+)\.")
        return {int(match.group(1)) for name in block if (match := pattern.match(name))}

    banks = indices(blocks[0], "l2_controllers")
    for index, block in enumerate(blocks[:roi], 1):
        found = indices(block, "l1_controllers")
        if found != set(range(cores)):
            raise ValueError(f"block {index}: L1 controller indices {sorted(found)} "
                             f"must equal {list(range(cores))}")
        found_banks = indices(block, "l2_controllers")
        if not found_banks:
            raise ValueError(f"block {index}: no L2 banks found")
        if found_banks != banks:
            raise ValueError(f"block {index}: L2 bank indices changed: {sorted(found_banks)} "
                             f"versus {sorted(banks)}")

    def total(name, integer=False):
        values = []
        for index, block in enumerate(blocks[:roi], 1):
            if name not in block:
                raise ValueError(f"missing expected stat {name} in block {index}")
            value = Decimal(block[name])
            if not value.is_finite() or value < 0 or (integer and value != value.to_integral_value()):
                raise ValueError(f"invalid stat {name}: {block[name]}")
            values.append(int(value) if integer else float(value))
        return sum(values)

    def counters(controller, index, cache):
        base = f"{PREFIX}{controller}{index}.{cache}.m_demand_"
        return total(base + "hits", True), total(base + "misses", True)

    row = {key: meta[key] for key in ("suite", "benchmark", "cores", "variant")}
    row["simSeconds"] = total("simSeconds")
    wall = meta.get("wall_seconds")
    if wall is not None and (not isinstance(wall, (int, float)) or not math.isfinite(wall) or wall < 0):
        raise ValueError("run.json wall_seconds must be finite and nonnegative")
    row["wall_seconds"] = wall if wall is not None else ""
    row["instructions"] = sum(total(f"board.processor.cores{core}.core.commitStats0.numInsts", True)
                              for core in range(cores))
    l1_hits = l1_misses = 0
    accesses = []
    for core in range(cores):
        hits, misses = counters("l1_controllers", core, "L1Dcache")
        l1_hits += hits
        l1_misses += misses
        accesses.append(hits + misses)
        if hits + misses == 0:
            print(f"WARNING: {run}: core{core} has zero L1D accesses", file=sys.stderr)
        if core < 8:
            row[f"core{core}_L1D_accesses"] = hits + misses
            row[f"core{core}_L1D_miss_rate"] = misses / (hits + misses) if hits + misses else 0
    row["L1D_imbalance"] = max(accesses) / min(accesses) if min(accesses) else ""
    l2 = [counters("l2_controllers", bank, "L2cache") for bank in sorted(banks)]
    for field, suffix in (("L1D_prefetch_hits", "numHits"),
                          ("L1D_prefetch_misses", "numMissedPrefetchedBlocks")):
        names = [f"{PREFIX}l1_controllers{core}.prefetcher.RubyPrefetcher.{suffix}"
                 for core in range(cores)]
        # Entirely absent optional stats stay blank. Partial presence is invalid:
        # summing only present cores/frames would silently undercount.
        row[field] = (sum(total(name, True) for name in names)
                      if any(name in block for name in names for block in blocks[:roi]) else "")
    for label, hits, misses in (("L1D", l1_hits, l1_misses),
                                ("L2", sum(x[0] for x in l2), sum(x[1] for x in l2))):
        row.update({f"{label}_hits": hits, f"{label}_misses": misses,
                    f"{label}_accesses": hits + misses,
                    f"{label}_miss_rate": misses / (hits + misses) if hits + misses else 0})
        row[f"{label}_MPKI"] = (1000 * misses / row["instructions"]
                                 if row["instructions"] else "")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--validate", action="store_true", help="validate a single run before writing DONE")
    args = parser.parse_args()
    if args.validate:
        try:
            parse_run(args.directory)
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
            print(f"ERROR: {args.directory}: {error}", file=sys.stderr)
            return 1
        return 0
    rows, errors = [], 0
    for done in sorted(args.directory.glob("*/DONE")):
        run = done.parent
        if (run / "FAILED").exists():
            done.unlink()
            continue
        try:
            rows.append(parse_run(run))
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
            print(f"WARNING: {run.name}: {error}", file=sys.stderr)
            done.unlink()
            (run / "FAILED").write_text(f"parsing failed: {error}\n")
            errors += 1
    temporary = args.directory / "summary.csv.tmp"
    with temporary.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(args.directory / "summary.csv")
    failures = [f"{p.parent.name}: {p.read_text().strip()}" for p in sorted(args.directory.glob("*/FAILED"))]
    (args.directory / "failed.txt").write_text("\n".join(failures) + ("\n" if failures else ""))
    print(f"Wrote {args.directory / 'summary.csv'} ({len(rows)} rows)")
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())

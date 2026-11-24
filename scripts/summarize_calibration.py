#!/usr/bin/env python3
"""Make one CSV for the eight Phase 2 workloads at each candidate input size."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parse_stats import FIELDS
from scripts.run_provenance import sha256
from scripts.staged_workload import experiment_layout, experiment_stdin, resolve_args

TIERS = {
    "s0": "experiments_v2.conf",
    "s1": "experiments_sizing_s1.conf",
    "s2": "experiments_sizing_s2.conf",
}
OWNERS = {
    "pr": "person1", "OCEAN-CONT": "person1", "FFT": "person1",
    "bfs": "person2", "OCEAN-NOCONT": "person2", "RADIX": "person2",
    "BARNES": "person3", "LU-NOCONT": "person3",
}
HASHES = ["config_sha256", "experiments_conf_sha256", "gem5_source_tree_sha256",
          "gem5_sha256", "benchmark_sha256", "stdin_sha256"]
REQUIRED_STATS = ["wall_seconds", "peak_rss_kib", "simTicks", "sim_seconds_from_ticks",
                  "instructions", "IPC", "L1D_MPKI", "L2_MPKI"]


def rows(data, batch):
    config_hash = sha256(ROOT / "mesi_two_level_se_multi.py")
    expected_hashes = {}
    barnes_fields = ("infile", "bodies", "seed", "outfile", "dt", "softening", "tolerance",
                     "cell_factor", "leaf_factor", "stop_time", "output_interval", "workers")
    for tier, filename in TIERS.items():
        conf = ROOT / filename
        variant = f"cal-l1fix-{batch}-{tier}"
        conf_hash = sha256(conf)
        for line in conf.read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            suite, bench, template, roi, timeout = line.split("|")
            args = template.replace("{cores}", "4")
            row = dict(tier=tier, runner=OWNERS[bench], variant=variant, suite=suite,
                       benchmark=bench, cores=4, seed=5489, input_args=args,
                       timeout_seconds=int(timeout), correctness_status="PENDING")
            job = f"{suite}_{bench}_c4"
            stdin_hash = ""
            if "<" in shlex.split(args):
                path = Path(shlex.split(resolve_args(args, ROOT))[-1])
                stdin = experiment_stdin(path, bench, 4)
                stdin_hash = hashlib.sha256(stdin.encode()).hexdigest()
                row["stdin_parameters"] = json.dumps(dict(zip(barnes_fields, stdin.splitlines(),
                                                               strict=True)))
            source = data / variant / f"{job}.json"
            failure = source.with_suffix(".failed")
            if not source.is_file():
                if failure.is_file():
                    row.update(correctness_status="RUN_FAILED",
                               correctness_detail=failure.read_text().strip())
                yield row
                continue

            exported = json.loads(source.read_text())
            meta, stats = exported["run"], exported["stats"]
            if any(meta[key] != row[key] for key in (
                    "variant", "suite", "benchmark", "cores", "seed", "runner", "timeout_seconds")):
                raise ValueError(f"{source}: metadata differs from the calibration plan")
            if (meta["roi"], meta["extra_args"], meta["config_sha256"],
                    meta["experiments_conf_sha256"], meta["args"]) != (
                    int(roi), "", config_hash, conf_hash, resolve_args(args, meta["repo_root"])):
                raise ValueError(f"{source}: workload or simulator configuration differs")
            if meta["repo_dirty"]:
                raise ValueError(f"{source}: calibration ran from a dirty checkout")
            for field, scope in (("repo_commit", "batch"),
                                 ("gem5_source_tree_sha256", "batch"),
                                 ("gem5_sha256", row["runner"]),
                                 ("benchmark_sha256", bench)):
                value = meta[field]
                if expected_hashes.setdefault((field, scope), value) != value:
                    raise ValueError(f"{source}: {field} differs for {scope}")
            if any(stats.get(key) in ("", None) for key in REQUIRED_STATS):
                raise ValueError(f"{source}: missing required calibration statistics")
            if any(stats[key] <= 0 for key in ("simTicks", "instructions", "peak_rss_kib")):
                raise ValueError(f"{source}: expected positive ROI ticks, instructions and RSS")
            if (meta.get("stdin_sha256") or "") != stdin_hash:
                raise ValueError(f"{source}: staged input does not match the plan")
            guest = experiment_layout(suite, bench, 4, meta["args"], source.parent)
            if meta["guest"] != guest:
                raise ValueError(f"{source}: staged guest command differs from the plan")
            workload = [meta["benchmark_sha256"], guest, stdin_hash]
            evidence = exported.get("correctness", {})
            row.update(stats)
            row.update({key: meta.get(key, "") for key in HASHES})
            row.update(repo_commit=meta["repo_commit"],
                       workload_sha256=hashlib.sha256(
                           json.dumps(workload, sort_keys=True).encode()).hexdigest(),
                       correctness_status=evidence.get("status", "UNVERIFIED"),
                       correctness_detail=evidence.get("error", evidence.get("method", "")))
            yield row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = list(rows(args.data, args.batch))
        writer = csv.DictWriter(sys.stdout, fieldnames=[
            "tier", "input_args", "stdin_parameters", "correctness_status", "correctness_detail", "runner", "seed",
            "timeout_seconds", *FIELDS, "repo_commit", *HASHES, "workload_sha256",
        ], lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"ERROR: {error}")

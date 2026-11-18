"""Generate run metadata and validate existing run directories before dispatch."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

if __package__:
    from .staged_workload import experiment_layout, resolve_args
else:
    from staged_workload import experiment_layout, resolve_args

VARIANT_FIELDS = ("gem5_sha256", "seed", "config_sha256")
GUARD_FIELDS = (*VARIANT_FIELDS, "benchmark_sha256", "args", "extra_args", "roi",
                "suite", "benchmark", "cores", "variant", "guest")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gem5_commit(binary):
    source = os.environ.get("GEM5_ROOT")
    candidates = [Path(source)] if source else binary.resolve().parents
    for root in candidates:
        if (root / "src/python/pybind11/core.cc").is_file() and (root / ".git").exists():
            return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                           text=True).strip()
    raise ValueError("cannot locate gem5 source checkout; set GEM5_ROOT")


def gem5_build_info(binary):
    output = subprocess.check_output([str(binary), "--build-info"], text=True)
    options = dict(re.findall(r"^ +([A-Za-z0-9_]+) = (.*)$", output, re.MULTILINE))
    isas = sorted(match[1] for option, value in options.items()
                  if value == "True" and (match := re.fullmatch(r"USE_(.+)_ISA", option)))
    protocol = options.get("PROTOCOL", "").strip()
    if not isas or not protocol:
        raise ValueError(f"{binary}: --build-info lacks enabled ISAs or PROTOCOL")
    return {"gem5_isa": ",".join(isas), "gem5_protocol": protocol}


def retryable(run):
    return (not run.is_symlink() and run.is_dir()
            and ((run / "FAILED").exists()
                 or not all((run / file).is_file() for file in ("DONE", "stats.txt", "run.json"))))


def archive_failed(run):
    if not retryable(run):
        raise ValueError(f"{run}: no longer eligible for --retry-failed")
    archive = run.parent / "_failed"
    if archive.is_symlink():
        raise ValueError(f"{archive}: refusing symlink archive")
    archive.mkdir(exist_ok=True)
    while True:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = archive / f"{run.name}.{timestamp}"
        if not destination.exists() and not destination.is_symlink():
            break
    run.rename(destination)
    print(f"ARCHIVE {run} -> {destination}", flush=True)


def check_existing(run, expected, retry_failed=False):
    if not run.exists() and not run.is_symlink():
        return
    if retry_failed and retryable(run):
        return True
    try:
        if (run.is_symlink() or not (run / "DONE").is_file()
                or not (run / "stats.txt").is_file() or (run / "FAILED").exists()):
            raise ValueError("existing directory is not a finished run")
        actual = json.loads((run / "run.json").read_text())
        if not isinstance(actual, dict):
            raise ValueError("run.json must contain an object")
        mismatches = [field for field in GUARD_FIELDS
                      if field not in actual or actual[field] != expected[field]]
        if mismatches:
            raise ValueError("missing or different fields: " + ", ".join(mismatches))
    except (OSError, ValueError) as error:
        raise ValueError(f"{run}: {error}; use a new --variant") from error


def preflight(repo, base, state, gem5, conf, runner, seed, extra, tasks, retry="0"):
    repo, base, state, gem5, conf = map(Path, (repo, base, state, gem5, conf))

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    common = dict(gem5_bin=str(gem5), gem5_commit=gem5_commit(gem5),
                  gem5_sha256=sha256(gem5),
                  config_sha256=sha256(repo / "mesi_two_level_se_multi.py"),
                  experiments_conf_sha256=sha256(conf), seed=int(seed),
                  runner=runner, nproc=int(subprocess.check_output(["nproc"])),
                  kernel=os.uname().release, repo_commit=git("rev-parse", "HEAD"),
                  repo_dirty=bool(git("status", "--porcelain")), repo_root=str(repo),
                  extra_args=extra, **gem5_build_info(gem5))
    items = Path(tasks).read_bytes().decode().split("\0")[:-1]
    hashes = {}
    names = set()
    retries = []
    for suite, bench, args, roi, _, core in zip(*(iter(items),) * 6, strict=True):
        name = f"{suite}_{bench}_c{core}"
        if name in names:
            raise ValueError(f"duplicate run directory name: {name}")
        names.add(name)
        binary = repo / "benchmarks" / suite / ("bin-roi" if roi == "1" else "bin") / bench
        if binary not in hashes:
            hashes[binary] = sha256(binary)
        meta = dict(common, suite=suite, benchmark=bench, cores=int(core), variant=base.name,
                    roi=int(roi), args=resolve_args(args.replace("{cores}", core), repo),
                    benchmark_sha256=hashes[binary])
        run = base / name
        meta["guest"] = experiment_layout(suite, bench, core, meta["args"], run)
        if check_existing(run, meta, retry_failed=retry == "1"):
            retries.append(run)
        (state / f"{name}.json").write_text(json.dumps(meta))
    # Finish validating the sweep before moving any prior attempts.
    for run in retries:
        archive_failed(run)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "commit":
            print(gem5_commit(Path(sys.argv[2])))
        elif sys.argv[1] == "check":
            run, metadata = map(Path, sys.argv[2:])
            check_existing(run, json.loads(metadata.read_text()))
        else:
            preflight(*sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"ERROR: {error}")

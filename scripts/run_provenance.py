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
TREE_FIELDS = ("gem5_source_tree_sha256", "gem5_source_file_count")
GUARD_FIELDS = (*VARIANT_FIELDS, *TREE_FIELDS, "benchmark_sha256", "args", "extra_args", "roi",
                "suite", "benchmark", "cores", "variant", "guest")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gem5_source_root(binary):
    source = os.environ.get("GEM5_ROOT")
    if source is not None:
        return Path(source)
    for path in binary.resolve().parents:
        if (path / "SConstruct").is_file() or (path / "src/python/pybind11/core.cc").is_file():
            return path
    raise ValueError("cannot locate gem5 source tree; set GEM5_ROOT")


def gem5_commit(root):
    if not (root / ".git").exists():
        return None
    try:
        git = ["git", "-C", str(root)]
        head = subprocess.check_output(git + ["rev-parse", "--show-prefix", "--verify", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL)
        match = re.fullmatch(r"\n([0-9a-f]{40}|[0-9a-f]{64})\n", head)
        if match and subprocess.check_output(git + ["cat-file", "-t", match[1]],
                                             text=True, stderr=subprocess.DEVNULL) == "commit\n":
            return match[1]
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


def gem5_source_provenance(root):
    script = Path(__file__).resolve().with_name("tree_hash.sh")
    summary = subprocess.check_output([str(script), str(root)], text=True)
    tree, count = (line.split()[1] for line in summary.splitlines())
    return dict(zip(TREE_FIELDS, (tree, int(count)), strict=True))


def gem5_build_info(binary):
    output = subprocess.check_output([str(binary), "--build-info"], text=True)
    options = dict(re.findall(r"^[ \t]+([A-Za-z0-9_]+) = ([^\n]*)$", output, re.MULTILINE))
    if not options:
        raise ValueError(f"{binary}: --build-info lacks build options")
    isas = sorted(match[1] for option, value in options.items()
                  if value == "True" and (match := re.fullmatch(r"USE_(.+)_ISA", option)))
    return {"gem5_isa": ",".join(isas), "gem5_protocol": options.get("PROTOCOL"),
            "gem5_build_options": options}


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


def check_existing(run, expected, retry_failed=False, *, fields=GUARD_FIELDS, warn=True):
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
        missing_tree_fields = [field for field in TREE_FIELDS
                               if field in fields and field not in actual]
        mismatches = [field for field in fields if field not in missing_tree_fields
                      and (field not in actual or actual[field] != expected[field])]
        if mismatches:
            raise ValueError("missing or different fields: " + ", ".join(mismatches))
        if warn and missing_tree_fields:
            print(f"WARNING: {run}: missing {', '.join(missing_tree_fields)}", file=sys.stderr)
    except (OSError, ValueError) as error:
        raise ValueError(f"{run}: {error}; use a new --variant") from error


def preflight(repo, base, state, gem5, conf, runner, seed, extra, tasks, retry="0"):
    repo, base, state, gem5, conf = map(Path, (repo, base, state, gem5, conf))
    source = gem5_source_root(gem5)
    source_provenance = gem5_source_provenance(source)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    common = dict(gem5_bin=str(gem5), gem5_git_commit=gem5_commit(source),
                  gem5_sha256=sha256(gem5),
                  config_sha256=sha256(repo / "mesi_two_level_se_multi.py"),
                  experiments_conf_sha256=sha256(conf), seed=int(seed),
                  runner=runner, nproc=int(subprocess.check_output(["nproc"])),
                  kernel=os.uname().release, repo_commit=git("rev-parse", "HEAD"),
                  repo_dirty=bool(git("status", "--porcelain")), repo_root=str(repo),
                  extra_args=extra, **source_provenance, **gem5_build_info(gem5))
    items = Path(tasks).read_bytes().decode().split("\0")[:-1]
    hashes = {}
    names = set()
    retries = []
    for suite, bench, args, roi, limit, core in zip(*(iter(items),) * 6, strict=True):
        name = f"{suite}_{bench}_c{core}"
        if name in names:
            raise ValueError(f"duplicate run directory name: {name}")
        names.add(name)
        binary = repo / "benchmarks" / suite / ("bin-roi" if roi == "1" else "bin") / bench
        if binary not in hashes:
            hashes[binary] = sha256(binary)
        meta = dict(common, suite=suite, benchmark=bench, cores=int(core), variant=base.name,
                    roi=int(roi), timeout_seconds=int(limit), args=resolve_args(args.replace("{cores}", core), repo),
                    benchmark_sha256=hashes[binary])
        run = base / name
        meta["guest"] = experiment_layout(suite, bench, core, meta["args"], run)
        if check_existing(run, meta, retry_failed=retry == "1"):
            retries.append(run)
        (state / f"{name}.json").write_text(json.dumps(meta))
    # A filtered sweep still shares provenance with the variant's completed runs.
    for run in sorted(base.iterdir()):
        if (run.name not in names and not run.name.startswith(".") and run.name != "_failed"
                and run.is_dir() and not run.is_symlink() and not retryable(run)):
            check_existing(run, common, fields=TREE_FIELDS)
    # Finish validating the sweep before moving any prior attempts.
    for run in retries:
        archive_failed(run)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "commit":
            print(gem5_commit(gem5_source_root(Path(sys.argv[2]))) or "null")
        elif sys.argv[1] == "check":
            run, metadata = map(Path, sys.argv[2:])
            check_existing(run, json.loads(metadata.read_text()), warn=False)
        else:
            preflight(*sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"ERROR: {error}")

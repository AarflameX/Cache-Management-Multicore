"""Build the SE process description and launch it in a private, fixed cwd."""
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def layout(suite, bench, core, tokens, stdin, origin, *, standalone=False):
    cwd = Path("/tmp/cmm-run") / f"{suite}_{bench}_c{core}"
    binary = cwd / "bin" / bench
    copies = {}
    args = list(tokens)
    for i, arg in enumerate(args):
        path = Path(arg)
        if path.is_absolute() or (standalone and (origin / path).is_file()):
            target = cwd / "args" / str(i) / path.name
            copies[target] = origin / path
            args[i] = str(target)
    if stdin:
        copies[cwd / "stdin.in"] = Path(stdin)
    sidecars = {"WATER-NSQUARED": "random.in", "WATER-SPATIAL": "random.in",
                "VOLREND": "head.den", "VOLREND-NPL": "head.den",
                "RAYTRACE": "inputs/teapot.geo"}
    if suite == "splash4" and bench in sidecars:
        sidecar = sidecars[bench]
        copies[cwd / sidecar] = origin / sidecar
    guest = dict(cwd=str(cwd), executable=str(binary), argv=[str(binary), *args],
                 env=[f"OMP_NUM_THREADS={int(core)}", "OMP_WAIT_POLICY=PASSIVE", "GOMP_SPINCOUNT=1"],
                 stdin=str(cwd / "stdin.in") if stdin else None,
                 staged_inputs=list(map(str, copies)))
    return guest, copies


def resolve_args(template, repo):
    # Expand inside each token so a space or quote in the checkout path is literal.
    return shlex.join(token.replace("{repo}", str(repo)) for token in shlex.split(template))


def experiment_layout(suite, bench, core, args, out):
    tokens = shlex.split(args)
    stdin = None
    if "<" in tokens:
        index = tokens.index("<")
        if index != len(tokens) - 2:
            raise ValueError("expected final '< file'")
        stdin = out / "stdin.in"
        tokens = tokens[:index]
    return layout(suite, bench, core, tokens, stdin, out)[0]


def private_dir(path):
    path.mkdir(mode=0o700, exist_ok=True)
    st = path.lstat()
    if st.st_uid != os.getuid() or st.st_mode != 0o40700:
        raise ValueError(f"expected private staging directory owned by current user: {path}")


def launch(repo, gem5, suite, bench, core, source, stdin, *tokens):
    origin = Path.cwd()
    experiment = os.environ.get("EXPERIMENT_GEM5_ADAPTER") == "1"
    if len(tokens) == 1 and not experiment:
        tokens = shlex.split(tokens[0])
    guest, copies = layout(suite, bench, core, tokens, stdin, origin, standalone=not experiment)
    if experiment and guest != json.loads((origin / "run.json").read_text())["guest"]:
        raise ValueError("guest workload differs from run.json")
    cwd = Path(guest["cwd"])
    private_dir(cwd.parent)
    private_dir(cwd)
    # Lock the stable directory inode. gem5 retains the lock if the launcher dies.
    lock = os.open(cwd, os.O_DIRECTORY)
    fcntl.flock(lock, fcntl.LOCK_EX)
    for path in cwd.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    for target, src in {Path(guest["executable"]): source, **copies}.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    options = [] if experiment else ["--outdir=" + str(origin / "m5out")]
    command = [os.path.abspath(gem5), *options, repo + "/mesi_two_level_se_multi.py",
               "--binary", guest["executable"], "--cores", core, "--env-json", json.dumps(guest["env"])]
    if stdin:
        command.extend(["--input", guest["stdin"]])
    status = subprocess.run([*command, "--literal-args", "--args", *guest["argv"][1:]],
                            cwd=cwd, pass_fds=(lock,)).returncode
    for path in cwd.iterdir():
        if path.is_file() and path not in copies:
            shutil.copy2(path, origin / path.name)
    return status if status >= 0 else 128 - status


if __name__ == "__main__":
    sys.exit(launch(*sys.argv[1:]))

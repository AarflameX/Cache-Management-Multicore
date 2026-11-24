#!/usr/bin/env python3
"""Run a separate correctness check for a completed calibration measurement."""

import argparse
from contextlib import nullcontext
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from check_cache_indexing import check
from run_provenance import sha256

ROOT = Path(__file__).resolve().parents[1]
PASS = {
    "bfs": r"^Verification:\s+PASS$",
    "pr": r"^Verification:\s+PASS$",
    "FFT": r"^TEST PASSED$",
    "LU-NOCONT": r"^TEST PASSED$",
    "RADIX": r"^PASSED: All keys in place\.$",
}


def run_log(command, work, name, timeout, stdin=None):
    with (stdin.open("rb") if stdin else nullcontext()) as source:
        with (work / name).open("w") as log:
            subprocess.run(command, cwd=work, stdin=source or subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)
    output = (work / name).read_text(errors="replace")
    failure = r"^(?:.*\b(?:fatal|panic):|ERROR:|FAILED:|TEST FAILED|Verification:\s+FAIL)"
    if re.search(failure, output, re.MULTILINE | re.IGNORECASE):
        raise ValueError(f"failure reported in {work / name}")
    return output


def ocean(output):
    match = re.search(r"Error tolerance\s*:\s*(\S+)", output)
    if not match:
        raise ValueError("missing OCEAN solver tolerance")
    tolerance = float(match[1])
    solves = [(int(level), float(residual)) for level, residual in re.findall(
        r"^iter\s+\d+, level\s+(\d+), residual norm\s+(\S+), work =", output, re.M)]
    if not solves or not all(0 <= residual < tolerance for _, residual in solves):
        raise ValueError("OCEAN must report finite converged residuals")
    return solves


def barnes(output, stdin):
    fields = stdin.read_text().splitlines()
    bodies = int(fields[1])
    dt, stop = float(fields[4]), float(fields[9])
    time, steps = 0.0, 0
    while time < stop + 0.1 * dt:
        time += dt
        steps += 1
    headers = re.findall(r"^BARNES_CHECK (\d+) (\S+) (\d+)$", output, re.M)
    if len(headers) != 1:
        raise ValueError("expected one BARNES snapshot header")
    count, t, nstep = headers[0]
    if int(count) != bodies or int(nstep) != steps or not math.isclose(float(t), time):
        raise ValueError("incorrect BARNES body count or final timestep")
    particles = []
    for line in re.findall(r"^BARNES_BODY (.+)$", output, re.M):
        index, *values = line.split()
        state = tuple(map(float, values))
        if int(index) != len(particles) or len(state) != 7 or not all(map(math.isfinite, state)):
            raise ValueError("invalid BARNES body state")
        particles.append(state)
    if (len(particles) != bodies or not all(p[0] > 0 for p in particles)
            or not math.isclose(sum(p[0] for p in particles), 1.0)):
        raise ValueError("incomplete BARNES snapshot or unexpected total mass")
    return particles


def verify(run, gem5, barnes_binary):
    if not (run / "DONE").is_file() or (run / "FAILED").exists():
        raise ValueError("verification requires a completed measurement")
    meta = json.loads((run / "run.json").read_text())
    if (meta["cores"], meta["seed"], meta["roi"], meta["extra_args"]) != (4, 5489, 1, ""):
        raise ValueError("measurement must be a four-core, seed-5489 baseline ROI")
    config = ROOT / "mesi_two_level_se_multi.py"
    bench = meta["benchmark"]
    measured = ROOT / "benchmarks" / meta["suite"] / "bin-roi" / bench
    if (sha256(gem5), sha256(config), sha256(measured)) != (
            meta["gem5_sha256"], meta["config_sha256"], meta["benchmark_sha256"]):
        raise ValueError("current gem5, config or benchmark differs from the measurement")
    check(run, 4)

    work = run / "verification"
    work.mkdir(exist_ok=True)
    evidence = run / "correctness.json"
    stdin = run / "stdin.in" if meta["guest"]["stdin"] else None
    if stdin and sha256(stdin) != meta["stdin_sha256"]:
        raise ValueError("staged stdin differs from the measured input")
    timeout = meta["timeout_seconds"]
    args = meta["guest"]["argv"][1:]
    environment = meta["guest"]["env"]
    result = dict(status="FAIL", measurement_sha256=sha256(run / "run.json"))
    try:
        if bench == "BARNES":
            binary = native_binary = barnes_binary
        elif bench.startswith("OCEAN-"):
            binary = measured
            native_binary = ROOT / "benchmarks/splash4/bin" / bench
            args = [*args, "-o"]
        else:
            binary = measured
            native_binary = None
            args = [*args, "-v" if meta["suite"] == "gap" else "-t"]

        command = [str(gem5), "-d", str(work / "m5out"), str(config), "--binary", str(binary),
                   "--cores", "4", "--seed", "5489", "--env-json", json.dumps(environment)]
        if stdin:
            command.extend(["--input", str(stdin)])
        simulated = run_log([*command, "--literal-args", "--args", *args],
                            work, "gem5.log", timeout)
        if not re.search(r"^Exiting @ tick \d+ because exiting with last active thread context",
                         simulated, re.M):
            raise ValueError("guest did not reach normal process exit")
        result["verification_binary_sha256"] = sha256(binary)
        result["gem5_log_sha256"] = sha256(work / "gem5.log")
        if native_binary:
            native = run_log(["env", *environment, str(native_binary), *args],
                             work, "native.log", timeout, stdin)
            result["native_binary_sha256"] = sha256(native_binary)
            result["native_log_sha256"] = sha256(work / "native.log")
        if bench == "BARNES":
            actual, reference = barnes(simulated, stdin), barnes(native, stdin)
            if any(a[0] != b[0] or any(not math.isclose(x, y, rel_tol=1e-8, abs_tol=1e-10)
                                      for x, y in zip(a[1:], b[1:]))
                   for a, b in zip(actual, reference)):
                raise ValueError("BARNES final positions or velocities differ from native")
            result["method"] = "final particle state vs native"
        elif bench.startswith("OCEAN-"):
            actual, reference = ocean(simulated), ocean(native)
            if (len(actual) != len(reference) or
                    any(level != native_level or not math.isclose(residual, native_residual,
                                                                 rel_tol=1e-5, abs_tol=1e-12)
                        for (level, residual), (native_level, native_residual) in zip(actual, reference))):
                raise ValueError("OCEAN residual sequence differs from native")
            result["method"] = "final residual of each multigrid solve vs native"
        else:
            if len(re.findall(PASS[bench], simulated, re.M)) != 1:
                raise ValueError(f"{bench} did not report exactly one verifier pass")
            result["method"] = "upstream built-in verifier"
        result["status"] = "PASS"
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    evidence.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{bench}: {result['status']} ({evidence})")
    return result["status"] == "PASS"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--gem5-bin", type=Path,
                        default=os.environ.get("GEM5_BIN", Path.home() / "gem5/build/X86/gem5.opt"))
    parser.add_argument("--barnes-bin", type=Path,
                        default=ROOT / "results/calibration-tools/BARNES")
    args = parser.parse_args()
    try:
        sys.exit(0 if verify(args.run.resolve(), args.gem5_bin.resolve(), args.barnes_bin.resolve())
                 else 1)
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"ERROR: {error}")

# Four-core input calibration

Use the same clean calibration commit on all three machines. It must include the
L1 fix from `ca91180`. Use the pinned gem5 v25.1.0.1 X86/MESI_Two_Level build
and the shared ROI binary archive from [teammate setup](TEAMMATE_SETUP.md).
The baseline has four simulated timing cores, seed 5489, 64-byte lines, private
32 KiB 2-way L1I/L1D caches at index bit 6, and two 256 KiB 8-way L2 banks at
index bit 7. Prefetching is disabled.

| Benchmark | S0 | S1 | S2 |
| --- | --- | --- | --- |
| GAP PR and BFS | `-g 14 -n 1` | `-g 15 -n 1` | `-g 16 -n 1` |
| OCEAN-CONT and OCEAN-NOCONT | `-p4 -n66` | `-p4 -n130` | `-p4 -n258` |
| FFT | `-p4 -m16` | `-p4 -m18` | `-p4 -m20` |
| RADIX | `-p4 -n262144 -r1024` | `-p4 -n1048576 -r1024` | `-p4 -n4194304 -r1024` |
| BARNES | 512 bodies | 2,048 bodies | 6,144 bodies |
| LU-NOCONT | `-p4 -n256 -b16` | `-p4 -n400 -b16` | `-p4 -n640 -b16` |

The runner expands `{cores}` and `{repo}`, selects the ROI binaries, and
stages BARNES stdin with four workers. S0 uses the configured wall timeouts
of 3,600 seconds for GAP and 1,800 seconds for Splash-4. S1 and S2 allow
14,400 seconds per job.

## Cross-machine preflight

From the repository root, start Bash and set the paths if they differ from the
defaults. Use a common new `BATCH` string for this round. Use one calibration
shell per machine and pause other simulations, builds, reference runs and heavy
host work while measuring.

```bash
export GEM5_ROOT="${GEM5_ROOT:-$HOME/gem5}"
export GEM5_BIN="${GEM5_BIN:-$GEM5_ROOT/build/X86/gem5.opt}"
export BATCH=round01
git rev-parse HEAD
git status --porcelain
git merge-base --is-ancestor ca91180 HEAD
python3 -m unittest
/usr/bin/time --version
./scripts/tree_hash.sh "$GEM5_ROOT"
sha256sum -c "$HOME/roi-benchmarks.sha256"
./scripts/verify_env.sh "$GEM5_BIN"
./tests/run_cache_index_probe.sh
./scripts/cross_machine_check.sh "$(hostname)-cal-$BATCH"
```

The team compares the checkout commit, source tree fingerprint and count,
ROI archive hashes, and the three smoke ROI digests by job ID. The three smoke
jobs are BFS, OCEAN-CONT, and FFT. If a digest differs, inspect the first ROI
block and rerun the affected smoke on each machine under a new smoke name to
distinguish repeatable differences from run-to-run variability. Resolve the
difference before treating machine results as comparable. Record each machine's
CPU model, host OS and kernel, usable memory or WSL/cgroup limit, and available
memory and swap at the start of each tier. Compare host runtime and RSS across
tiers on the same machine. On Linux, `free -k`, `lscpu`, and the
`pswpin`/`pswpout` counters in `/proc/vmstat` provide the host checks.
For a cgroup v2 quota, also read the job cgroup's `memory.max` and
`memory.current`. Send these host notes with the tier archive.

Run only your own build command for native reference checks. Build from the
pinned sources in [teammate setup](TEAMMATE_SETUP.md).

```bash
# Person 1
ENABLE_ROI=0 ./benchmarks/splash4/build.sh OCEAN-CONT
# Person 2
ENABLE_ROI=0 ./benchmarks/splash4/build.sh OCEAN-NOCONT
# Person 3
ENABLE_ROI=0 BARNES_VERIFY_DIR="$PWD/results/calibration-tools" ./benchmarks/splash4/build.sh BARNES
```

## Measure one tier at a time

Paste this function in the same shell. It rejects a reused variant directory
before launching. Passing `--dry-run` as the fifth argument previews the jobs.
Calibration paths are under `results/calibration/<person>/cal-l1fix-<batch>-<tier>/`.

```bash
cal_run() {
  local person=$1 tier=$2 conf=$3 filter=$4
  local results="results/calibration/$person"
  local variant="cal-l1fix-$BATCH-$tier"
  shift 4
  if [[ ${1:-} != --dry-run && -n $(git status --porcelain) ]]; then
    printf 'Use the agreed clean calibration commit.\n' >&2
    return 1
  fi
  if [[ -e "$results/$variant" || -L "$results/$variant" ]]; then
    printf 'Result directory already exists: %s/%s\n' "$results" "$variant" >&2
    return 1
  fi
  ./run_experiment.sh --conf "$conf" --variant "$variant" --results "$results" \
    --gem5-bin "$GEM5_BIN" --cores 4 --seed 5489 --jobs 1 --host-rss \
    --runner "$person" --filter "$filter" "$@"
}
```

Paste **only one line at a time**, starting with S0. Before using the next
line, verify and share the completed tier and apply the progression criteria
below. To preview a line, append `--dry-run`.

**Person 1**

```bash
cal_run person1 s0 experiments_v2.conf '^(pr|OCEAN-CONT|FFT)$'
cal_run person1 s1 experiments_sizing_s1.conf '^(pr|OCEAN-CONT|FFT)$'
cal_run person1 s2 experiments_sizing_s2.conf '^(pr|OCEAN-CONT|FFT)$'
```

**Person 2**

```bash
cal_run person2 s0 experiments_v2.conf '^(bfs|OCEAN-NOCONT|RADIX)$'
cal_run person2 s1 experiments_sizing_s1.conf '^(bfs|OCEAN-NOCONT|RADIX)$'
cal_run person2 s2 experiments_sizing_s2.conf '^(bfs|OCEAN-NOCONT|RADIX)$'
```

**Person 3**

```bash
cal_run person3 s0 experiments_v2.conf '^(BARNES|LU-NOCONT)$'
cal_run person3 s1 experiments_sizing_s1.conf '^(BARNES|LU-NOCONT)$'
cal_run person3 s2 experiments_sizing_s2.conf '^(BARNES|LU-NOCONT)$'
```

For a held workload, narrow the anchored filter before starting the next tier.
For a fresh repeat, agree on a new `BATCH` and preserve the original artifacts.
Check each runner's final status and `failed.txt` even if a job finishes early.

## Check results and package one tier

Run only after measurements have stopped. Set `PERSON` to your assignment
and `TIER` to the finished tier. The verification tool checks paired
`config.ini`/`config.json` against the corrected geometry for every measured
job and uses its recorded input, including the staged BARNES stdin. It runs
one verification case at a time and retains its evidence under
`verification/` and `correctness.json` in the measured run directory.

| Benchmark | Separate correctness run and pass condition |
| --- | --- |
| BFS | `-v`, upstream serial BFS validates reachability and parents for the generated graph and source. Require `Verification: PASS`. |
| PR | `-v`, upstream verifier checks PageRank residual for the generated graph. Require `Verification: PASS`. |
| FFT | `-t`, forward plus inverse FFT and checksum. Require `TEST PASSED`. The inverse changes the instrumented ROI, so use the ordinary forward-only measurement. |
| LU-NOCONT | `-t`, solve with the factors and check against the known solution. Require `TEST PASSED`. |
| RADIX | `-t`, upstream sorted-key check after digit passes. Require `PASSED: All keys in place.` |
| OCEAN-CONT and OCEAN-NOCONT | `-o`, record the final residual for each multigrid solve. Require finite residuals below the configured tolerance and match the native run's solve count, levels and residuals (relative tolerance `1e-5`, absolute `1e-12`). |
| BARNES | Run the same diagnostic binary natively and under gem5. Check final timestep, body count, finite states and total mass. Compare every body's mass, position and velocity in stable body-array order (position and velocity relative tolerance `1e-8`, absolute `1e-10`). The diagnostic build prints its snapshot after the workers join. |

```bash
PERSON=person1  # set to person1, person2 or person3
TIER=s0         # set to s0, s1 or s2
(
  set -euo pipefail
  variant="cal-l1fix-$BATCH-$TIER"
  measured="results/calibration/$PERSON/$variant"
  handoff="results/calibration/handoff/$PERSON"
  test -d "$measured"
  mkdir -p "$handoff/$variant"
  for run in "$measured"/*_c4; do
    [[ -d "$run" ]] || continue
    if [[ -f "$run/FAILED" ]]; then
      cp -- "$run/FAILED" "$handoff/$variant/${run##*/}.failed"
    elif [[ -f "$run/DONE" ]]; then
      if ! python3 scripts/verify_calibration.py "$run"; then
        printf 'Review correctness evidence for %s\n' "$run" >&2
      fi
      ./scripts/export_run.py "$run" --data "$handoff"
    fi
  done
  artifact="$PERSON-$variant.tar.gz"
  tar -C "$handoff" -czf "$handoff/$artifact" "$variant"
  (cd "$handoff" && sha256sum "$artifact" > "$artifact.sha256")
  printf '%s\n' "$handoff/$artifact" "$handoff/$artifact.sha256"
)
```

## Consolidate and decide

Send the printed archive and checksum through the team's shared channel or
folder. Keep raw configs, stats, and correctness logs locally for investigation.
The coordinator places the pairs under `results/calibration/inbox/` and runs
the following block once per tier. Job IDs are unique across assignments.
Only the coordinator writes the consolidated CSV in the ignored results tree,
so teammates can keep working on the same code commit.

```bash
TIER=s0   # repeat for s1 and s2 after collecting those tiers
(
  set -euo pipefail
  variant="cal-l1fix-$BATCH-$TIER"
  output="$PWD/results/calibration/merged-$BATCH"
  mkdir -p "$output"
  cd results/calibration/inbox
  for person in person1 person2 person3; do
    artifact="$person-$variant.tar.gz"
    sha256sum -c "$artifact.sha256"
    tar -xzf "$artifact" -C "$output" --keep-old-files
  done
  cd ../../..
  python3 scripts/summarize_calibration.py "$BATCH" --data "$output" > "$output/calibration.csv.tmp"
  mv -- "$output/calibration.csv.tmp" "$output/calibration.csv"
  python3 scripts/check_variant.py "$output/$variant"
)
```

Share `calibration.csv` with the team. It includes all 24 planned rows, their
input arguments and correctness states, and metrics as results arrive.
`RUN_FAILED` carries the runner's reason, `UNVERIFIED` means a valid statistics
export has no correctness evidence, and `PENDING` means there is no export or
failure marker. A held case can remain pending, with the reason recorded in
the team's decision notes.

`wall_seconds` is elapsed host time for staging and the measured simulation.
`peak_rss_kib` is GNU time's maximum RSS for the gem5 process. Simulated seconds
are also computed from ROI `simTicks / simFreq`, avoiding rounded display
precision. IPC is summed committed instructions divided by summed simulated
core cycles over the selected ROI. MPKI uses committed instructions from the
same ROI. `L1_replacements` counts the controller replacement event across both
L1I and L1D. The summary carries separate clean and other L2 replacement event counts across
both banks, plus their sum when both are available. These are protocol event
indicators. Missing optional
replacement and coherence counters stay blank. The four existing coherence
counter pairs are described in [statistics mapping](stats_mapping.md).
The workload hash covers the measured executable hash, normalized guest
argv/environment and the staged stdin hash when applicable. The simulator
config and tier file hashes have separate columns.

### Criteria for S0 → S1 and S1 → S2

Review each benchmark independently using these preparation defaults.

1. Require matching preflight evidence, corrected geometry on every controller,
   four cores, seed 5489, disabled prefetching, and the agreed workload and config
   hashes. The team records explicit reasons for missing or failed cases.
2. Require a completed simulation, validated ROI statistics, a correctness
   `PASS`, positive ticks and instructions, and the required host performance
   and MPKI fields. Hold any workload with a timeout, failure, missing required
   statistics, or a numerical mismatch.
3. Require an isolated host run with no OOM or swap activity. As a planning
   margin, require measured peak RSS below 70% of the machine's available
   memory at launch, accounting for any lower WSL/cgroup limit. Estimate the
   next tier's memory from its allocation sizes and available memory. Require
   a conservative next-tier wall time estimate below 80% of its timeout using
   the [work ratios](SIZING.md) for S0 → S1 and the observed growth for
   S1 → S2. Treat these bounds as calibration gates, and record any exception.
4. Compare instruction growth, L1D/L2 MPKI, and replacement and coherence
   indicators across completed tiers. Investigate unexpected scaling or
   unexplained counter gaps before increasing an input. A low miss rate alone
   does not decide whether the next candidate is suitable. Record the decision
   per benchmark and tier before beginning the next set.

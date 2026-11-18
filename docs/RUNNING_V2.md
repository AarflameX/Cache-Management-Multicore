# Running baseline v2 across three machines

Run your block from the repository root. Start from the same clean checkout
containing `experiments_v2.conf` and the provenance scripts. Use the agreed gem5
and ROI benchmark binaries on all three machines. If gem5 lives outside the
default location, add `--gem5-bin /path/to/gem5.opt` to your runner command.
Set `GEM5_ROOT` if the executable is outside its gem5 source checkout.

The runner applies `--filter` to the benchmark name in the second conf column.
Each filter uses `^…$` to match full names. Result directories use the
`<suite>_<benchmark>_c4` format, which the export commands below use explicitly.
To preview your jobs, add `--dry-run` to the runner command and run that command
by itself.

All three people publish to `results/baseline-v2`. Coordinate so only one
person runs the push command at a time. The push script switches branches,
rebases an existing results branch, and commits changes under `data/`, so keep
the working tree clean outside `data/` and keep unrelated data changes out of
the checkout.

## Person 1

```bash
(
  set -e
  ./run_experiment.sh --conf experiments_v2.conf --variant baseline-v2 --cores "4" \
    --seed 5489 --runner person1 --filter '^(pr|OCEAN-CONT|FFT)$'
  ./scripts/export_run.py results/baseline-v2/gap_pr_c4
  ./scripts/export_run.py results/baseline-v2/splash4_OCEAN-CONT_c4
  ./scripts/export_run.py results/baseline-v2/splash4_FFT_c4
  ./scripts/push_results.sh baseline-v2
)
```

## Person 2

```bash
(
  set -e
  ./run_experiment.sh --conf experiments_v2.conf --variant baseline-v2 --cores "4" \
    --seed 5489 --runner person2 --filter '^(bfs|OCEAN-NOCONT|RADIX)$'
  ./scripts/export_run.py results/baseline-v2/gap_bfs_c4
  ./scripts/export_run.py results/baseline-v2/splash4_OCEAN-NOCONT_c4
  ./scripts/export_run.py results/baseline-v2/splash4_RADIX_c4
  ./scripts/push_results.sh baseline-v2
)
```

## Person 3

```bash
(
  set -e
  ./run_experiment.sh --conf experiments_v2.conf --variant baseline-v2 --cores "4" \
    --seed 5489 --runner person3 --filter '^(BARNES|LU-NOCONT)$'
  ./scripts/export_run.py results/baseline-v2/splash4_BARNES_c4
  ./scripts/export_run.py results/baseline-v2/splash4_LU-NOCONT_c4
  ./scripts/push_results.sh baseline-v2
)
```

Once all three pushes are on the results branch, run
`./scripts/merge_summaries.py baseline-v2` from an up-to-date checkout of that
branch to generate `data/baseline-v2/summary.csv`.

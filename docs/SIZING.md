# Four-core baseline-v2 sizing

Run S1 first. Compare the four-core results before choosing S2 for overnight
runs. The sizing configs use the same eight ROI benchmarks and set a 14,400-second
wall timeout per job. The commands below use fresh variants for both tiers
so the runner cannot skip jobs completed with the old L1 indexing.
The configuration creates two 256 KiB L2 banks
(512 KiB aggregate). Array sizes below describe data footprints. Cache residency
also depends on access order, sharing, and bank mapping.

## Candidate inputs

| Workload | v1 | S1 | S2 | Approximate S1 / S2 work relative to v1 |
|---|---|---|---|---|
| GAP bfs and pr | `-g 14 -n 1` | `-g 15 -n 1` | `-g 16 -n 1` | 2× / 4× generated vertices and input edges at fixed degree |
| OCEAN-CONT and OCEAN-NOCONT | `-n66` | `-n130` | `-n258` | 4× / 16× interior grid points at fixed solver settings |
| BARNES | 512 bodies | 2,048 bodies | 6,144 bodies | 4.9× / 16.8× using bodies × log₂(bodies) at fixed timestep count |
| LU-NOCONT | `-n256 -b16` | `-n400 -b16` | `-n640 -b16` | 3.8× / 15.6× cubic factorization work |
| FFT | `-m16` | `-m18` | `-m20` | 4.5× / 20× using points × log₂(points), with 4× / 16× the points |
| RADIX | `-n262144 -r1024` | `-n1048576 -r1024` | `-n4194304 -r1024` | 4× / 16× keys at fixed radix and digit count |

The four-core v1 summary recorded roughly 3–4.5 minutes for these Splash-4 jobs
and 11–14 minutes for GAP. A linear extrapolation from the work ratios puts
many Splash S1 jobs around 15–19 minutes and S2 around 59–67 minutes. GAP
extrapolates to about 23–29 minutes for S1 and 46–57 minutes for S2. These are
sizing estimates. Host contention with three concurrent jobs, memory traffic,
PageRank convergence, and OCEAN multigrid iterations can change the wall time.
Use the pilot results to choose the tier per job.

A single S1 OCEAN double grid is about 132 KiB and the solver works across
multiple grids. The S1 LU matrix is about 1.22 MiB. An S1 FFT complex array
contains 4 MiB of unpadded data, and the two S1 RADIX key arrays total 16 MiB.
The S1 BARNES body array is 256 KiB on x86-64 before tree and work arrays. Its
S2 body array alone is 768 KiB. Measure the ROI L2 miss rate to determine how
much of each footprint creates cache pressure.

## Source-checked constraints

The Splash-4 references below are in the source checkout used by
`benchmarks/splash4/build.sh`, under `benchmarks/splash4/src/Splash-4/`.

- **FFT.** `-m M` is an even exponent with `2^M` complex points. `-p P` is a
  positive power of two and `2^(M/2) >= P`. The code uses signed-int shifts
  such as `1 << M`, so at four workers the shift-safe even range is 4–30,
  subject to the padding checks and available memory. The selected 18 and 20
  use default cache-line parameters. See `fft/fft.c.in:138–240`.
- **OCEAN-CONT and OCEAN-NOCONT.** `-n N` is the square grid dimension,
  `N = 2^k + 2`, and `-p P` is a positive power of two. CONT factors workers
  into subgrids and needs a viable coarse level with at least two interior
  grid points per worker in each dimension. Four workers split 2×2 here.
  NOCONT also checks `IMAX` and `MAX_LEVELS`; the x86-64 build uses
  `IMAX = JMAX = 8098` and `MAX_LEVELS = 14`, making 4098 the largest
  dimension passing the grid-size rule. That limit describes the built-in
  arrays, with memory and runtime imposing practical limits. See
  `ocean-contiguous_partitions/main.c.in:164–255` and
  `ocean-non_contiguous_partitions/main.c.in:132–194`, `decs.h.in:17–25`.
- **LU-NOCONT.** Use positive matrix dimension `-n N`, block width
  `-b B`, and worker count `-p P`. The code rounds the block count up and
  clips edge tiles, so `N` may be nondivisible by `B`. Both tiers use
  multiples of 16 to retain full 16×16 tiles. Matrix storage is
  `N*N*sizeof(double)`. See `lu-non_contiguous_blocks/lu.c.in:117–165` and
  `lu-non_contiguous_blocks/lu.c.in:488–555`.
- **RADIX.** `-n N` takes a positive key count parsed with `atoi` (stay
  within signed-int range and available memory). The active code partitions
  using quotient and remainder, so a power-of-two key count is optional.
  Keep at least as many keys as workers. `-r R` must be a power of two.
  Use 2 through 4096 because radix 1 prevents the digit-count loop from
  terminating and the prefix arrays have `MAX_RADIX = 4096` entries. Keep
  the four workers, a power of two for the binary prefix tree and within
  `MAX_PROCESSORS = 1024`. `-m` controls the maximum key and pass count.
  The tiers leave it at the default 67,108,864 and keep `-r1024`. See
  `radix/radix.c.in:44–86`, `:137–227`, `:241–264`, `:509–550`, and
  `:700–715`.
- **BARNES.** Its positional stdin parameters take a blank first line to
  generate bodies internally, a positive body count on line 2, and a workload
  seed on line 3. The fourth line stays blank to avoid an output snapshot.
  Lines 5–11 hold timestep, softening, tolerance, allocation ratios, stop
  time, and output interval. Line 12 is the worker count, replaced by the
  runner with `{cores}`. The implementation allocates bodies dynamically
  and sizes the tree using `fleaves * nbody` and `fcells * maxleaf`.
  `MAX_PROC` bounds its worker array at 1024. The existing repo inputs
  are `barnes-small.in` (256) and `barnes-512.in`. The source checkout also
  ships `barnes/inputs/n8k-p4` and `barnes/inputs/n16384-p4`, among other
  processor-count and PARSEC presets. See `barnes/code.c.in:27–64`,
  `:364–382`, `:471–501`, `barnes/getparam.c.in:40–75`,
  `barnes/defs.h.in:22–23`, and `run_experiment.sh`'s stdin staging.

## Build and input preparation

No size change requires a rebuild for these candidates. Use the existing
x86-64 ROI binaries in each suite's `bin-roi/`. OCEAN-NOCONT's 130 and 258
fit the current compile-time dimensions.

The candidate BARNES files `benchmarks/splash4/inputs/barnes-2048.in` and
`barnes-6144.in` are included. They keep seed 123 and every physics and
allocation parameter from `barnes-512.in`, with the body count on line 2 and
four workers on line 12. To recreate the exact files from the repository root:

```sh
for n in 2048 6144; do
  sed -e "2s/.*/$n/" -e '12s/.*/4/' benchmarks/splash4/inputs/barnes-512.in \
    > "benchmarks/splash4/inputs/barnes-${n}.in"
done
```

## Run in tmux

From the repository root, open a persistent shell with:

```sh
tmux new-session -s sizing-v2
```

Inside tmux, set the runner name and run S1:

```sh
RUNNER="$(hostname)"
./run_experiment.sh --conf experiments_sizing_s1.conf --variant sizing-s1-l1fix \
  --cores "4" --jobs 3 --seed 5489 --runner "$RUNNER"
```

Run S2 once S1 finishes, using the same machine and runner name for a comparable
measurement:

```sh
./run_experiment.sh --conf experiments_sizing_s2.conf --variant sizing-s2-l1fix \
  --cores "4" --jobs 3 --seed 5489 --runner "$RUNNER"
```

Detach with `Ctrl+B` followed by `D`. Reattach with
`tmux attach-session -t sizing-v2`. Add `--dry-run` to either runner command
to print the scheduled jobs without launching gem5.

## Compare completed jobs

The command reads the runner's two summaries. Miss rates are fractions.
Blank optional counters print as `NA`. A failed or incomplete job has no
summary row, and its failure may be listed in the tier's `failed.txt`.

```sh
python3 - <<'PY'
import csv
import sys
from pathlib import Path

fields = ("wall_seconds", "instructions", "simSeconds", "L1D_MPKI",
          "L1D_miss_rate", "L2_miss_rate", "L1_invalidations_per_kinst")
table = [("variant", "job", *fields)]
for variant in ("sizing-s1-l1fix", "sizing-s2-l1fix"):
    path = Path("results") / variant / "summary.csv"
    if not path.is_file():
        print(f"Missing summary: {path}", file=sys.stderr)
        continue
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            job = f"{row['suite']}_{row['benchmark']}_c{row['cores']}"
            values = []
            for field in fields:
                value = row.get(field, "")
                if not value:
                    values.append("NA")
                elif field == "instructions":
                    values.append(value)
                else:
                    values.append(f"{float(value):.6g}")
            table.append((variant, job, *values))
table[1:] = sorted(table[1:], key=lambda row: (row[1], row[0]))
widths = [max(map(len, column)) for column in zip(*table)]
for row in table:
    print("  ".join(f"{value:<{width}}" for value, width in zip(row, widths)).rstrip())
PY
```

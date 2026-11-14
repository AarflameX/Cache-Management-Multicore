# Multicore cache management

gem5 v25.1.0.1, built with PROTOCOL=MESI_Two_Level, CPU type TIMING

After cloning, install the benchmark build dependencies on Linux x86-64:

```bash
# Fedora
sudo dnf install git gcc gcc-c++ make m4 glibc-static libstdc++-static

# Ubuntu
sudo apt-get update
sudo apt-get install git build-essential m4
```

Build gem5 separately with the setup above. The runner defaults to
`~/gem5/build/X86/gem5.opt`. If your executable is elsewhere, set:

```bash
export GEM5_BIN=/absolute/path/to/gem5.opt
```

Run both suite build scripts once after cloning (network access is required):

```bash
./benchmarks/gap/build.sh
./benchmarks/splash4/build.sh
```

They clone [GAP](https://github.com/sbeamer/gapbs) and
[SPLASH-4](https://github.com/OdnetninI/Splash-4) into their suite's `src/`
directory, build statically, and install executables into `bin/`. Existing
checkouts are reused on subsequent builds. GAP installs `bfs`, `pr`, `cc`,
`sssp`, `bc`, and `tc`; SPLASH-4 installs 15 executables, including `LU-CONT`,
`FFT`, `RADIX`, `BARNES`, and `OCEAN-CONT`.

Run small workloads:

```bash
./run_benchmark.sh --suite gap --benchmark bfs --args "-g 10 -n 1"
./run_benchmark.sh --suite splash4 --benchmark LU-CONT --cores 2 --args "-p2 -n128 -b16"
```

`--cores` defaults to 2 and must be a positive multiple of the two L2 banks.
Put `--args` last; use separate tokens or one string with shell-style quoting
(no shell expansion). Match workload thread-count arguments to `--cores`.
OpenMP workloads receive `OMP_NUM_THREADS`, `OMP_WAIT_POLICY=PASSIVE`, and
`GOMP_SPINCOUNT=1` to allow workers to park promptly before process exit.

The simulated memory capacity is **4 GiB** by default, set by `--mem-size` in
`mesi_two_level_se_multi.py`. RAYTRACE at 8 cores exhausted the previous 2 GiB
capacity. This changes capacity only; the single-channel DDR4-2400 timing model
is unchanged. Pass `--mem-size SIZE` before the config's `--args` when invoking
gem5 directly, or use the experiment runner's `--extra-args "--mem-size 2GiB"`
to override it. `run_benchmark.sh` does not set a memory size.

The runner works from any directory. gem5 writes `m5out/`, including
`stats.txt`, in the current working directory. Both sample runs were verified
to exit with status 0 and produce non-empty stats. Generated sources, binaries,
`results/`, and `m5out/` are ignored by Git and must be regenerated locally.

For GAP kernel-only statistics, build the x86 m5ops library once, then enable
ROI instrumentation (an optional kernel list limits which binaries are built):

```bash
(cd ~/gem5/util/m5 && scons build/x86/out/libm5.a)
ENABLE_ROI=1 ./benchmarks/gap/build.sh bfs
./run_benchmark.sh --suite gap --benchmark bfs --roi --cores 2 --args "-g 10 -n 1"
```

`GEM5_ROOT` overrides `~/gem5` for benchmark headers and libm5. ROI binaries
install into `benchmarks/gap/bin-roi/`, leaving `bin/` untouched. With
`ENABLE_ROI` unset or zero, builds use the usual `bin/` and omit m5ops.
Instrumented binaries must run under gem5; instruction-based m5ops cannot
run directly on the host. SPLASH-4 is unchanged.

Each GAP trial resets statistics immediately before the kernel and dumps them
immediately afterward, excluding graph generation, verification, and analysis.
The reset does not flush caches. gem5 also emits a final exit dump, so use the
first block for the first trial (`-n 1` requests one trial):

```bash
awk '/Begin Simulation Statistics/ {printing=1} printing {print} /End Simulation Statistics/ && printing {exit}' m5out/stats.txt
```

Additional suites should follow this layout, with `build.sh` resolving paths
relative to itself and installing Linux x86-64 executables into `bin/`:

```text
benchmarks/<suite>/
  src/
  build.sh
  bin/
```

## Running experiments

`experiments.conf` lists `suite|benchmark|args|roi|timeout_sec`; see the benchmark
inputs table below for sizing measurements and pending cases. Lines starting
with `#` are ignored. `{cores}` matches workload workers to the simulated cores;
`{repo}` expands to this checkout. A final `< file` selects stdin. The runner
stages private input/data files and updates worker counts in the supplied
WATER, BARNES, and FMM stdin files, without changing the originals.

```bash
./run_experiment.sh --dry-run
./run_experiment.sh --filter '^bfs$' --cores "2" --variant test
./run_experiment.sh --cores "2 4 8" --jobs 4
./run_experiment.sh --cores "2 4 8" --variant candidate --extra-args ""
```

Run sweeps inside **tmux with the laptop plugged in**. The default core list is
`2 4 8`; core counts must be positive and even. `--extra-args` forwards flags
before the config's `--args`; the current config has no cache-tuning flags and rejects unsupported options. A variant
names an output directory; it does not itself change the simulated hardware.

Each run writes its own `results/<variant>/<suite>_<benchmark>_c<cores>/`,
including `run.log`, `stats.txt`, and metadata. Successful, validated runs get
`DONE` and are skipped on reruns. Failures/timeouts get `FAILED` and are retried.
Use a new variant when changing inputs, options, or binaries: resume identifies
runs by suite, benchmark, cores, and variant, not by a configuration hash.
Concurrent sweeps into the same variant are locked out.

`results/<variant>/summary.csv` includes every DONE run; `failed.txt` lists
failures. Regenerate them with `python3 parse_stats.py results/<variant>`.
The parser requires one ROI dump plus the exit dump, or three frame dumps plus
the exit dump for VOLREND/VOLREND-NPL; it aggregates ROI demand hits/misses and
omits the exit dump. Non-ROI conf records require one exit block. Missing stats
or unexpected block counts fail validation and exclude the run from the CSV.
The sweep exits nonzero if failures remain.

`run.json` records the executable path and 12-character SHA-256 prefix, repository
commit and dirty flag, resolved benchmark args, extra config args, UTC start
timestamp, and elapsed wall time. `roi` is stored as an integer. Legacy metadata
is accepted; absent wall time stays blank. The CSV also reports committed
instructions, L1D/L2 MPKI, L1D access imbalance (max/min), and optional Ruby
prefetch counters. Zero-access cores produce a warning and blank imbalance;
zero instructions produce blank MPKI. L1 controllers must match the requested
cores exactly; every discovered L2 bank is aggregated.

Run parser fixtures without gem5 with `python3 -m unittest`.

## Benchmark inputs

Arguments below use `{cores}` for the worker count and `{repo}` for the checkout.
Input filenames are relative to `benchmarks/splash4/inputs/`; `<` means stdin.
The original 4-core measurements were taken with **4 jobs in parallel**.
The CHOLESKY ladder and patched GAP measurements are detailed below with their
concurrency context. 8-core times have not yet been measured. Resized cases need
confirmation where marked.

| Suite | App | Args/input | 4-core wall time | Notes |
| --- | --- | --- | --- | --- |
| GAP | bfs | `-g 14 -n 1` | 860 s | |
| GAP | bc | `-g 14 -n 1` | 863 s | |
| GAP | cc | `-g 14 -n 1` | 1026.55 s | Chunk 256; imbalance 1.578×; before/after below |
| GAP | pr | `-g 14 -n 1` | 1237.17 s | Chunk 256; imbalance 1.013×; before/after below |
| GAP | sssp | `-g 14 -n 1` | 1030 s | |
| GAP | tc | `-g 12 -n 1` | resized, pending confirmation | Other GAP kernels use `-g 14` |
| SPLASH-4 | FFT | `-p{cores} -m16` | 236 s | |
| SPLASH-4 | LU-CONT | `-p{cores} -n256 -b16` | 266 s | |
| SPLASH-4 | LU-NOCONT | `-p{cores} -n256 -b16` | 283 s | |
| SPLASH-4 | RADIX | `-p{cores} -n262144 -r1024` | 281 s | |
| SPLASH-4 | OCEAN-CONT | `-p{cores} -n66` | resized, pending confirmation | |
| SPLASH-4 | OCEAN-NOCONT | `-p{cores} -n66` | resized, pending confirmation | |
| SPLASH-4 | WATER-NSQUARED | `< water-nsquared-125.in` | 441 s | 125 molecules |
| SPLASH-4 | WATER-SPATIAL | `< water-spatial-small.in` | 194 s | Minimum tested size; 125+ molecules timed out |
| SPLASH-4 | CHOLESKY | `-p{cores} -t {repo}/benchmarks/splash4/inputs/cholesky-grid2304.hb` | 491.31 s | 2,304 unknowns, side 48; 30.25M ROI instructions; factorization check passed |
| SPLASH-4 | BARNES | `< barnes-512.in` | 340 s | Inherently imbalanced |
| SPLASH-4 | FMM | `< fmm-1024.in` | 420 s | |
| SPLASH-4 | RAYTRACE | `-p{cores} {repo}/benchmarks/splash4/inputs/raytrace-small.env` | 664 s | |
| SPLASH-4 | VOLREND | `{cores} head 1` | 428 s | Private copy of upstream head data |
| SPLASH-4 | VOLREND-NPL | `{cores} head 1` | 441 s | Private copy of upstream head data |

RADIOSITY is excluded: under gem5 it did not complete within 40 minutes at
2 cores for either input tried (`-ae 5000 -en 0.05` and
`-ae 2000.0 -en 0.005`). Its ROI patches and build support remain; the patches
were validated natively.

The L2 is 256 KiB over 2 banks at every core count. SPLASH apps have near-zero
L2 miss rates, so L1D-side features mainly appear as L1-to-L2 latency and traffic
savings. GAP has real L2 misses (6–12%). CHOLESKY and BARNES are inherently
imbalanced; interpret aggregate cache results alongside per-core accesses.

### Generating CHOLESKY inputs

`cholesky-grid<N>.hb` is named by **unknown count / matrix order N**.
The generator's positional argument is the **side length**; N = side².
It writes the one-based lower-triangle Harwell-Boeing PSA pattern of a 2D
five-point Laplacian. CHOLESKY supplies numeric values itself. A side-s grid
has 3s²−2s stored nonzeros, or 5s²−4s after symmetric expansion.

The original `cholesky-grid64.hb` has side 8, order 64, and 176 stored nonzeros
(288 in the full symmetric matrix). Side 8 reproduces it byte for byte.
The earlier timed-out files named grid128/grid192/grid256 instead used those
numbers as side lengths: orders 16,384 / 36,864 / 65,536 with 48,896 / 110,208 /
196,096 stored nonzeros (81,408 / 183,552 / 326,656 full symmetric nonzeros).
Those files are no longer present; grid256 now means **256 unknowns, side 16**.
The previous side-256 run was archived separately under `results/` before
reusing the `chol256` variant name.

Regenerate the ladder with the tracked script:

```bash
python3 scripts/gen_cholesky_grid.py 16 benchmarks/splash4/inputs/cholesky-grid256.hb
python3 scripts/gen_cholesky_grid.py 24 benchmarks/splash4/inputs/cholesky-grid576.hb
python3 scripts/gen_cholesky_grid.py 32 benchmarks/splash4/inputs/cholesky-grid1024.hb
python3 scripts/gen_cholesky_grid.py 48 benchmarks/splash4/inputs/cholesky-grid2304.hb
python3 scripts/gen_cholesky_grid.py 64 benchmarks/splash4/inputs/cholesky-grid4096.hb
```

The ladder files are 6,338 / 14,027 / 24,831 / 55,783 / 99,194 bytes,
respectively, all below 5 MB. Files above 5 MB should be ignored and generated
on demand. Keep `-p{cores}` joined because CHOLESKY's filename scan does not
skip separate option values. `-t` requests its factorization check.

CHOLESKY ladder runs used four simulated cores, a 900-second timeout, and
`--jobs 4`, with one variant per input. At most four simulations ran at a
time; patched PR/CC started when only the two largest ladder cases remained.
Wall time includes setup, ROI, factorization checking, and exit.

| Unknowns | Side | Wall seconds | ROI instructions | L1D miss rate | L2 miss rate | Imbalance | Per-core L1D accesses (0 / 1 / 2 / 3) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 256 | 16 | 35.340226 | 828,143 | 20.5368% | 0.6229% | 2.2651× | 98,148 / 54,005 / 49,076 / 111,161 |
| 576 | 24 | 86.781080 | 3,476,415 | 19.4975% | 0.9124% | 1.6532× | 287,463 / 293,350 / 227,916 / 376,792 |
| 1,024 | 32 | 163.125294 | 8,577,619 | 22.3959% | 1.6853% | 1.2626× | 757,859 / 621,589 / 681,114 / 784,810 |
| 2,304 | 48 | 491.313782 | 30,254,451 | 22.3883% | 1.3354% | 1.4450× | 2,988,561 / 2,068,254 / 2,489,714 / 2,231,781 |
| 4,096 | 64 | 900.314095 (timeout) | unavailable | unavailable | unavailable | unavailable | unavailable |

All four completed runs printed factorization check `PASSED`. The 4,096 case
timed out with an empty stats file, so no ROI counters are available for it.
Grid2304 is the largest candidate that finished under 600 seconds with at
least 10M ROI instructions (491.31 s, 30.25M instructions). The config selects
it with timeout 1800. These results do not indicate a universal input hang.
Raw logs, stats, and metadata are in `results/chol256`, `results/chol576`,
`results/chol1024`, `results/chol2304`, and `results/chol4096`.

### GAP scheduling patch

`benchmarks/gap/chunks.patch` changes the dynamic chunk size from 16,384 to
256 in PR and CC. At `-g 14`, the nominal vertex count is 16,384, so the old
chunk covered the whole loop: the heavy loops were not parallel. A chunk of
256 yields 64 chunks, allowing four workers to share the work. The native
verification graph reported 16,381 vertices, which also fits one old chunk
and 64 new chunks.

The patch changes every dynamic pragma in these two kernels:

| Source location | Loop | ROI |
| --- | --- | --- |
| `pr.cc:45` | PageRank pull/update, with error reduction | Inside |
| `cc.cc:60` | Component compression | Inside |
| `cc.cc:107` | Sparse sampling link, both neighbor rounds | Inside |
| `cc.cc:124` | Final undirected link | Inside, undirected branch |
| `cc.cc:135` | Final directed link | Inside, directed branch |

All use `schedule(dynamic, 256)` after patching. CC's two final-link branches
are alternatives. Initializers without a schedule clause are unchanged.
CC retains its serial `SampleFrequentElement` phase (1,024 samples plus
histogram/max selection) inside the ROI. Graph construction, result analysis,
and verification remain outside the ROI.

The build script applies the scheduling patch with the same forward/reverse
`git apply --check` mechanism as the existing ROI patch, for **both normal and
ENABLE_ROI builds**. A fresh upstream checkout receives it automatically.
Both patches were checked together against a clean upstream archive; normal
and ROI builds succeeded. Normal four-thread PR and CC verification passed:

```bash
./benchmarks/gap/build.sh pr cc
OMP_NUM_THREADS=4 OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=1 benchmarks/gap/bin/pr -g 14 -n 1 -v
OMP_NUM_THREADS=4 OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=1 benchmarks/gap/bin/cc -g 14 -n 1 -v
ENABLE_ROI=1 ./benchmarks/gap/build.sh pr cc
```

PR reported total error 0.00004 and verification PASS; CC reported verification
PASS. Changing PR's in-place update order can affect convergence and instruction
count, so the before/after numbers describe each measured run.

The unpatched reference is `results/rest/summary.csv`; patched runs used
`-g 14 -n 1`, four simulated cores, variants `pr_patched` / `cc_patched`,
and 1,800-second timeouts. Both patched runs completed and passed statistics
validation. All per-core figures below are ROI L1D demand hits + misses.

| App | Version | ROI instructions | Wall seconds | L1D imbalance | Per-core L1D accesses (0 / 1 / 2 / 3) |
| --- | --- | ---: | ---: | ---: | --- |
| pr | Unpatched (chunk 16384) | 30,739,092 | 1142.303641 | 786.5608× | 12,344,285 / 15,696 / 15,952 / 15,694 |
| pr | Patched (chunk 256) | 28,226,325 | 1237.171296 | 1.0127× | 2,856,666 / 2,855,516 / 2,848,368 / 2,820,769 |
| cc | Unpatched (chunk 16384) | 2,171,519 | 854.446374 | 131.2099× | 302,668 / 353,742 / 2,954 / 2,696 |
| cc | Patched (chunk 256) | 2,182,520 | 1026.545435 | 1.5779× | 228,964 / 145,103 / 146,222 / 146,089 |

The scheduling patch substantially reduced access imbalance in both kernels.
CC still has a higher core-0 count, consistent with its serial sampling phase
and runtime overhead. PR distributes accesses almost evenly. The PR instruction count
also changed, consistent with its order-sensitive in-place updates.

Wall time increased in these runs. It includes unchanged graph setup, and
host concurrency was not identical throughout the before/after measurements:
the original measurements used four jobs in parallel; the new runs started
alongside the two largest CHOLESKY cases and later ran with fewer active jobs.
These wall times are not a controlled speedup comparison. Simulated ROI time
fell from 76.082 to 18.372 ms for PR, and from
3.725 to 1.334 ms for CC. Raw patched results remain in
`results/pr_patched` and `results/cc_patched`.

The dry-run emits two lines per scheduled run (an output-directory comment
and a command). Thus 20 apps × 3 core counts yield 60 commands but
`./run_experiment.sh --dry-run | wc -l` prints 120. The launcher is unchanged.

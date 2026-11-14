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
The supplied 4-core measurements were taken with **4 jobs in parallel**;
8-core times have not yet been measured. Resized cases need confirmation.

| Suite | App | Args/input | 4-core wall time | Notes |
| --- | --- | --- | --- | --- |
| GAP | bfs | `-g 14 -n 1` | 860 s | |
| GAP | bc | `-g 14 -n 1` | 863 s | |
| GAP | cc | `-g 14 -n 1` | 854 s | Large dynamic chunks cause imbalance |
| GAP | pr | `-g 14 -n 1` | 1142 s | Large dynamic chunks cause imbalance |
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
| SPLASH-4 | CHOLESKY | `-p{cores} -t {repo}/benchmarks/splash4/inputs/cholesky-grid64.hb` | 13 s (prior grid64); resized, pending confirmation | Enlarged candidates: all three timed out; retain grid64 fallback; inherently imbalanced |
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

No generator accompanied the original input (introduced in commit `b8d8c71`).
`cholesky-grid64.hb` is historically named for its **64 vertices**, an 8×8 grid.
The new filenames grid128/grid192/grid256 name the **side length** instead:
16,384 / 36,864 / 65,536 vertices. The generator writes a one-based symmetric
lower-triangle Harwell-Boeing PSA pattern of a 2D five-point Laplacian;
CHOLESKY supplies numeric values itself, matching the original convention.
All three generated files are under 5 MB (397,423 / 894,991 / 1,591,898 bytes)
and can be tracked. Reproduce them with:

```bash
python3 scripts/gen_cholesky_grid.py 8 /tmp/cholesky-grid64.hb
cmp benchmarks/splash4/inputs/cholesky-grid64.hb /tmp/cholesky-grid64.hb
python3 scripts/gen_cholesky_grid.py 128 benchmarks/splash4/inputs/cholesky-grid128.hb
python3 scripts/gen_cholesky_grid.py 192 benchmarks/splash4/inputs/cholesky-grid192.hb
python3 scripts/gen_cholesky_grid.py 256 benchmarks/splash4/inputs/cholesky-grid256.hb
```

The side-8 output was verified byte for byte against the original. Keep
`-p{cores}` joined because CHOLESKY's filename scan does not skip separate
option values. `-t` requests its factorization check.

CHOLESKY sizing used four simulated cores with variants `chol128`, `chol192`,
and `chol256`, each limited to 1,200 seconds. The clean reruns used finalized
input files; an earlier attempt interrupted after a header edit during input
reading was discarded. The three clean runs ran concurrently and overlapped
the four GAP wait-policy comparisons for their first ten minutes, so wall
measurements include that host contention.

| Grid side | Wall seconds | Result | ROI instructions | L1D miss rate | L2 miss rate | Imbalance | Per-core L1D accesses (0–3) |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| 128 | 1200.378491 | Timed out | unavailable | unavailable | unavailable | unavailable | unavailable |
| 192 | 1200.316519 | Timed out | unavailable | unavailable | unavailable | unavailable | unavailable |
| 256 | 1200.307357 | Timed out | unavailable | unavailable | unavailable | unavailable | unavailable |

Every stats file was empty at timeout: no completed ROI dump was available,
so ROI counters cannot be reported. None of the three enlarged grids finished,
and none meets the approximately 600-second / 10-million-instruction target.
The config therefore retains the known-working grid64 input with timeout 1800;
its prior 13-second / approximately 0.1-million-ROI-instruction result is only a
functional fallback. No larger usable input was established by these tests.
Raw logs and metadata remain under `results/chol128`, `results/chol192`, and
`results/chol256`. No additional sizing experiments or full sweep were run.

The dry-run emits two lines per scheduled run (an output-directory comment
and a command). Thus 20 apps × 3 core counts yield 60 commands but
`./run_experiment.sh --dry-run | wc -l` prints 120. The launcher is unchanged.

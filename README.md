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

`experiments.conf` lists `suite|benchmark|args|roi|timeout_sec`; inputs are
placeholders to finalize before collecting performance results. Lines starting
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

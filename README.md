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

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

Additional suites should follow this layout, with `build.sh` resolving paths
relative to itself and installing Linux x86-64 executables into `bin/`:

```text
benchmarks/<suite>/
  src/
  build.sh
  bin/
```

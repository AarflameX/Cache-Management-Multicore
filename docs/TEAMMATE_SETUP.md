# Teammate setup for Fedora and WSL2 Ubuntu

Use an x86-64 Linux environment and the same clean experiment-repo revision
as the other runners. Keep gem5 and the experiment checkout under your Linux
home directory. The guest benchmark executables must have matching SHA-256
hashes across teammates. Build the host gem5 executable locally from the
pinned source revision so it links against the host's libraries.

## Fedora

```bash
sudo dnf install -y git gcc gcc-c++ make m4 scons zlib-devel \
  protobuf-devel protobuf-compiler gperftools-devel python3-devel python3-pip \
  boost-devel pkgconf-pkg-config libpng-devel glibc-static libstdc++-static \
  binutils file tmux
```

## WSL2 Ubuntu

Use Ubuntu 24.04 LTS x86-64 in WSL2. In PowerShell, run
`wsl --list --verbose` and check that Ubuntu shows version 2. Inside Ubuntu:

```bash
uname -m  # expect x86_64
sudo apt-get update
sudo apt-get install -y git build-essential m4 scons zlib1g-dev \
  libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev \
  python3-dev python3-venv libboost-all-dev pkg-config libpng-dev \
  binutils file tmux
git config --global core.autocrlf false
```

Clone and build in Linux paths such as `~/gem5` and
`~/Cache-Management-Multicore`. Keep sources, binaries, temporary build files,
and results off `/mnt/c` and other Windows-mounted drives. Use Linux Git in
WSL and check out LF line endings. A fresh Linux checkout avoids carrying
CRLF files or lost executable bits over from a Windows checkout.
[Microsoft's WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop)

If the build is memory-constrained, edit `%UserProfile%\.wslconfig` in Windows.
For a host with at least 24 GB of RAM, an example allocation is:

```ini
[wsl2]
memory=16GB
swap=8GB
```

Adjust the cap to leave RAM for Windows. Save your work before running
`wsl --shutdown` in PowerShell, then reopen Ubuntu and check `free -h`.
If compilation is killed for lack of memory, resume the same SCons target
with `-j2`. The job limit controls host build parallelism.
[Microsoft's .wslconfig reference](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

For overnight runs, plug in the machine, disable automatic sleep on AC,
and configure the lid action if closing a laptop. In WSL, make these changes
in **Windows** power settings. Use `tmux` to survive terminal disconnects.
Keep the host awake and avoid updates or reboots during the run.

## Build the pinned gem5

Local shell history records the build command below with `-j6` after checkout
of `v25.1.0.1`. The local checkout resolves to
`c8222cc67a399bfc01e8658dd14b30d5bfd634f9`. At that commit, the target path
selects `build_opts/X86`, which sets `BUILD_ISA=y`, `USE_X86_ISA=y`, `RUBY=y`,
`PROTOCOL="MESI_Two_Level"`, and `RUBY_PROTOCOL_MESI_Two_Level=y`. Those
settings are also present in the local generated `build/X86/gem5.build/config`.
The command preserves the historical `PROTOCOL=...` argument. The pinned
X86 build preset provides the protocol setting in the generated config.

```bash
cd "$HOME"
git clone https://github.com/gem5/gem5.git
cd gem5
git checkout --detach c8222cc67a399bfc01e8658dd14b30d5bfd634f9
git describe --tags --exact-match  # v25.1.0.1
scons build/X86/gem5.opt PROTOCOL=MESI_Two_Level -j6
(cd util/m5 && scons build/x86/out/libm5.a)
export GEM5_ROOT="$HOME/gem5"
export GEM5_BIN="$GEM5_ROOT/build/X86/gem5.opt"
```

A v25.1.0.1 release tarball is fine if its source tree matches the pinned
fingerprint below. Never fake a git commit. Set `GEM5_ROOT` to the extracted
gem5 directory and build there using the same SCons commands.

The Fedora reference `gem5.opt` is dynamically linked, including against
Fedora's Python shared library. Fedora and Ubuntu builds can have different
gem5 executable hashes. Both should report version `25.1.0.1`,
`USE_X86_ISA = True`, and `RUBY_PROTOCOL_MESI_Two_Level = True` in
`--build-info`. An ALL build can report `PROTOCOL = MULTIPLE`.

## Install identical ROI workloads

Use one reference set of the eight benchmark executables. Transfer them in
a tar archive and verify the owner's checksums after extraction. Local rebuilds
with different GCC or glibc versions can produce different bytes even from the
same sources. The local workload source revisions are:

- GAPBS `941462c7c42e786e4e006a9211b0576ef78d23f7`
- Splash-4 `59949ac095c71b526c2367c95eaa936343ea4cfb`

If the owner needs to rebuild the reference set, start with clean source
checkouts at those revisions. From the experiment repo root, with
`GEM5_ROOT` set and `libm5.a` built, run:

```bash
ENABLE_ROI=1 ./benchmarks/gap/build.sh bfs pr
ENABLE_ROI=1 ./benchmarks/splash4/build.sh BARNES FFT LU-NOCONT \
  OCEAN-CONT OCEAN-NOCONT RADIX
```

Both build scripts already link statically and apply the repository's ROI patches.
The reference owner packages the files from the experiment repo root:

```bash
benchmarks=(benchmarks/gap/bin-roi/{bfs,pr}
  benchmarks/splash4/bin-roi/{BARNES,FFT,LU-NOCONT,OCEAN-CONT,OCEAN-NOCONT,RADIX})
sha256sum "${benchmarks[@]}" > /tmp/roi-benchmarks.sha256
tar -czf /tmp/roi-benchmarks.tar.gz "${benchmarks[@]}"
```

After receiving both files into `$HOME`, extract from the experiment repo root:

```bash
tar -xzf "$HOME/roi-benchmarks.tar.gz"
sha256sum -c "$HOME/roi-benchmarks.sha256"
file benchmarks/gap/bin-roi/bfs benchmarks/splash4/bin-roi/FFT
```

Expect `statically linked`. Avoid launching the ROI executables directly
on the host because their gem5 m5ops are intended for simulation.

## Verify each machine

From the experiment repo root, run these checks without launching a simulation:

```bash
./scripts/tree_hash.sh "$GEM5_ROOT"
"$GEM5_BIN" --build-info
sha256sum "$GEM5_BIN"
python3 -m unittest
./scripts/cross_machine_check.sh "$(hostname)" --dry-run
```

Run `scripts/tree_hash.sh <gem5 dir>` for your source directory and send the
two lines it prints. The pinned output is:

```text
tree_sha256 56a03a9961b9f08072b25768637502907977cd537dd614c95e351746e0c10546
files 7542
```

When ready to run verification workloads, use:

```bash
./scripts/verify_env.sh "$GEM5_BIN"
./tests/run_cache_index_probe.sh
./scripts/cross_machine_check.sh "$(hostname)-l1fix"
```

The two-core BFS smoke checks the effective geometry in both config dumps.
On the pinned local build its corrected ROI recorded `simSeconds = 0.000083`.
The x86-64 probe cycles through three lines four times. At a 64-byte stride
it expects three cold L1D misses and nine hits. At a 16 KiB stride all
three lines compete for two ways in one set, giving twelve misses.

The cross-machine check uses a fresh variant for the indexing fix and runs BFS
`-g 10 -n 1`, OCEAN-CONT `-n34`, and FFT `-m10` at four cores and seed
5489, using one job at a time in `results/xcheck-<runner>/`. Compare the
three printed SHA-256 digests by job ID across machines. The script hashes
the first statistics block, excluding lines whose stat name starts with
`host`, and leaves out the final exit dump. A mismatch means the retained
ROI text differs and should be investigated before pooling results.

After exporting the real runs, check the merged exports with:

```bash
./scripts/check_variant.py data/baseline-v2
```

Gem5 executable hashes can differ across runners in exported-data mode. The
checker reports those differences as informational and flags multiple hashes
under a single runner name.
The check requires matching gem5 source tree hashes, seeds, and simulator
config hashes across runners. It reports missing tree hashes in older exports,
commit differences, and build option differences as INFO. Each runner's
recorded build options must enable X86 and MESI_Two_Level. Extra ISAs and
protocols are allowed. Benchmark hashes
are compared per suite and benchmark, and workload args per suite, benchmark,
and core count when there are multiple records for that job. One record
per job has no peer args to compare, so use the same agreed conf on every
machine. Use fresh variants to collect the build-info fields for older runs
whose metadata predates them.

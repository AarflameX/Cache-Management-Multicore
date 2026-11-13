Optional ROI instrumentation covers FFT, LU-CONT, RADIX, and the batch 1 apps
listed below.
GAP is unchanged. The tracked `roi.patch` supplies a shared `roi.h` and changes
the upstream `.c.in` templates, so regenerated C retains the instrumentation.
The builder applies the patch once, checks libm5, and forces recompilation.
Without ENABLE_ROI, ROI_BEGIN()/ROI_END() are no-ops and libm5 is unnecessary.

Build from the repository root (GEM5_ROOT defaults to ~/gem5):

```sh
ENABLE_ROI=1 GEM5_ROOT="$HOME/gem5" benchmarks/splash4/build.sh FFT LU-CONT RADIX
```

This installs only into `benchmarks/splash4/bin-roi/`; `bin/` is untouched.
The gem5 tree must already contain `include/gem5/m5ops.h` and
`util/m5/build/x86/out/libm5.a`. To build the latter, run
`scons build/x86/out/libm5.a` from gem5's `util/m5` directory.

Run on two cores:

```sh
./run_benchmark.sh --suite splash4 --benchmark FFT --roi --cores 2 --args -p2 -m10
./run_benchmark.sh --suite splash4 --benchmark LU-CONT --roi --cores 2 --args -p2 -n512 -b16
./run_benchmark.sh --suite splash4 --benchmark RADIX --roi --cores 2 --args -p2 -n262144 -r1024
```

Why the boundaries are here:

- FFT: reset after each worker allocates/copies its twiddle array and touches
  its data, before the forward FFT. Dump after the forward transform (and the
  optional inverse transform when `-t` is requested), before timing results
  are stored or printed. The later serial checksum check is outside the ROI.
- LU-CONT: reset after matrix initialization, worker-local allocation, and
  TouchA, before `lu()` factors the matrix. Dump after all workers return from
  `lu()`, before timing results and the optional serial result check.
- RADIX: reset after every worker generates its keys, before the digit loop
  builds histograms, ranks, and scatters keys. Dump after all digit passes,
  before timing results and the optional serial sort check.

At entry, the existing barrier waits for every worker to finish initialization.
Only worker 0 calls ROI_BEGIN(), which resets gem5 statistics. A second barrier
holds all workers until that reset has completed; RADIX already had this second
barrier. At exit, a barrier waits for all parallel computation to finish (RADIX
already had it). Worker 0 alone calls ROI_END() to dump statistics. A following
barrier prevents other workers from storing results or returning to reporting
while that dump is pending. Existing algorithm barriers remain in place.
Barrier and timing bookkeeping at the boundaries is included in the measured
interval. Thread creation, input setup, result printing, and serial validation
are outside it. The explicit dump marks the ROI end; gem5 may also emit a later
statistics block when the process exits.

Validation: all three static ROI binaries build; the patch applies to a clean
upstream tree and is recognized on repeated builds. Native two-worker builds
without ENABLE_ROI passed FFT's inverse test, LU's factorization check, and
RADIX's sorted-key check with small inputs. Shell syntax checks passed.
No gem5 simulations were run.

Batch 1 additions use independent `roi-*.patch` files, applied with the same
forward/reverse checks as `roi.patch`. This also upgrades existing patched
checkouts without changing the original three apps or shared header.

LU-NOCONT (the upstream binary name for LU-NON-CONT): reset after worker-local
allocation and TouchA, once the existing barrier confirms setup is complete.
Dump after every worker returns from `lu()`, before timing/reporting. Added
barriers prevent factorization before reset and reporting before dump.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh LU-NOCONT
./run_benchmark.sh --suite splash4 --benchmark LU-NOCONT --roi --cores 2 --args -p2 -n32 -b8
```

LU-NOCONT validation: static ROI build and native two-worker 32x32 result
checks passed both with ROI disabled and with m5 logging stubs (one reset,
then one dump). No simulations were run.

OCEAN-CONT: reset after the `sl_onetime` barrier, which waits for all field,
forcing, and solver setup; measure the entire outer timestep loop, including
its first step. Dump after all workers finish the loop's final field updates,
before timing/reporting. Entry/exit barriers hold workers around thread 0's ops.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh OCEAN-CONT
./run_benchmark.sh --suite splash4 --benchmark OCEAN-CONT --roi --cores 2 --args -p2 -n18
```

OCEAN-CONT validation: static ROI build and native two-worker 18x18 runs passed
with ROI disabled and m5 logging stubs (one reset, then one dump).

OCEAN-NOCONT (the upstream binary name for OCEAN-NON-CONT): reset after the
`sl_onetime` barrier confirms all shared fields and forcing setup are ready.
Dump after the outer timestep loop and final field updates, before timing
results; entry/exit barriers synchronize all workers around thread 0's ops.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh OCEAN-NOCONT
./run_benchmark.sh --suite splash4 --benchmark OCEAN-NOCONT --roi --cores 2 --args -p2 -n18
```

OCEAN-NOCONT validation: static ROI build and native two-worker 18x18 runs passed
with ROI disabled and m5 logging stubs (one reset, then one dump).

WATER-NSQUARED: reset after the initial INTRAF/INTERF acceleration calculation
and its barrier, before timestep 1. Dump after all requested timesteps finish,
before returning to final reporting. Barriers hold all workers around ProcID 0's
ops; the existing periodic energy calculation/output remains inside the loop.

The runner's `--input` option passes a file to gem5's workload stdin. WATER
also opens `random.in` relative to its working directory, so run from its source
directory. From the repository root:

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh WATER-NSQUARED
repo="$PWD"
(cd "$repo/benchmarks/splash4/src/Splash-4/water-nsquared" && \
 "$repo/run_benchmark.sh" --suite splash4 --benchmark WATER-NSQUARED --roi --cores 2 \
 --input "$repo/benchmarks/splash4/inputs/water-nsquared-small.in")
```

The input uses 64 molecules, two steps, predictor order 6, no saves/restarts,
energy output every two steps, two workers, and the default cutoff. Both steps
are measured; this deliberately does not skip the first step as warmup.
WATER-NSQUARED validation: static ROI build and native runs passed with ROI
disabled and m5 logging stubs (one reset, then one dump), using that input.

WATER-SPATIAL: reset after per-worker box lists and initial accelerations are
ready at the pre-loop barrier. Dump after all timesteps, before MDMAIN returns
to final reporting; entry/exit barriers protect ProcID 0's ops. Periodic energy
output stays in the loop, as in WATER-NSQUARED.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh WATER-SPATIAL
repo="$PWD"
(cd "$repo/benchmarks/splash4/src/Splash-4/water-spatial" && \
 "$repo/run_benchmark.sh" --suite splash4 --benchmark WATER-SPATIAL --roi --cores 2 \
 --input "$repo/benchmarks/splash4/inputs/water-spatial-small.in")
```

The spatial input also uses 64 molecules and two steps with the default cutoff;
this creates 2x2x2 boxes, enough for two workers. WATER-SPATIAL validation:
static ROI build and native runs passed with ROI disabled and m5 logging stubs
(one reset, then one dump). Native checks are functional checks, not simulated
performance measurements.

Build all five batch 1 ROI binaries (leaving the original three and `bin/`
binaries untouched):

```sh
ENABLE_ROI=1 GEM5_ROOT="$HOME/gem5" benchmarks/splash4/build.sh \
  LU-NOCONT OCEAN-CONT OCEAN-NOCONT WATER-NSQUARED WATER-SPATIAL
```

Batch 1 integration checks: a fresh upstream archive accepted all patches and
built these five static ROI binaries twice, confirming repeat-build patch
checks. It created no `bin/` directory. Mock gem5 invocations verified runner
binary selection, two-core forwarding, and WATER stdin-file forwarding.
Shell syntax and config Python syntax checks passed. No simulations were run.

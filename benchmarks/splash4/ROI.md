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

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

Batch 2 adds CHOLESKY, BARNES, and FMM with separate patches; the original
apps and shared ENABLE_ROI macros are unchanged. Only worker 0 issues m5 ops.

CHOLESKY: reset after PreAllocateFO/PreProcessFO and the setup barrier, just
before BNumericSolveFO. Dump after every worker completes numeric factorization,
before timing/checks/reporting; entry and exit barriers hold workers around ops.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh CHOLESKY
./run_benchmark.sh --suite splash4 --benchmark CHOLESKY --roi --cores 2 \
  --args -p2 -t benchmarks/splash4/inputs/cholesky-grid64.hb
```

The tracked Harwell-Boeing pattern input is a 64x64 matrix for an 8x8 grid:
column c contains its diagonal, right grid neighbor (unless at the row edge),
and lower grid neighbor (unless on the bottom row), stored as a one-based lower
triangle in column order. CHOLESKY supplies numeric values itself. `-t` checks
the factorization result. Keep `-p2` joined: upstream's filename scan skips
option tokens but does not skip separate option values. The file is a small
functional workload, not a representative performance benchmark; upstream's
preprocessing efficiency diagnostic can be NaN when it assigns zero static
domains at this size, while the numeric result check passes.

CHOLESKY validation: static ROI build, native two-worker result checks with
ROI disabled and with m5 logging stubs passed (exactly one reset then one dump).
No simulations were run.

BARNES: reset after each worker initializes its body/cell/leaf tables and
find_my_initial_bodies finishes its barrier, before the timestep loop. Dump
after all workers leave the loop, before final statistics; barriers prevent
computation before reset and return/reporting before dump.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh BARNES
./run_benchmark.sh --suite splash4 --benchmark BARNES --roi --cores 2 \
  --input benchmarks/splash4/inputs/barnes-small.in
```

The tracked 12-line input uses 256 generated Plummer bodies, seed 123, no
particle input/output files, timestep 0.025, softening 0.05, tolerance 1.0,
cell/leaf allocation factors 2.0/5.0, stop time 0.075, output interval 0.25,
and two workers. Its first and fourth lines must remain blank. All timesteps
are included in the ROI; upstream's printed timing counters still skip the
first two steps and therefore cover a different interval.

BARNES validation: static ROI build and native two-worker runs with ROI disabled
and m5 logging stubs passed (exactly one reset then one dump).

FMM: reset after particle-list/box allocation and per-worker time initialization,
with the setup barrier ensuring everyone is ready, before the timestep loop.
Dump after all workers finish the loop, before timing aggregation/reporting;
barriers hold workers around thread 0's calls. First grid construction is work
inside the ROI, and all requested steps are measured.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh FMM
./run_benchmark.sh --suite splash4 --benchmark FMM --roi --cores 2 \
  --input benchmarks/splash4/inputs/fmm-small.in
```

The tracked nine-line input uses two Plummer clusters, 256 particles, precision
1e-6, two workers, three timesteps of duration 0.025, default softening (0.0),
and cost-zones partitioning. FMM writes a `times` file in the working directory.
Its upstream printed timing summary counts steps 3 onward; the ROI includes
all three steps. Native checks ran in temporary directories to contain this
output. FMM validation: static ROI build and native runs with ROI disabled and
m5 logging stubs passed (exactly one reset then one dump).

Build all three batch 2 ROI binaries without rebuilding completed apps:

```sh
ENABLE_ROI=1 GEM5_ROOT="$HOME/gem5" benchmarks/splash4/build.sh CHOLESKY BARNES FMM
```

Batch 2 integration validation: a fresh upstream archive accepted all ROI
patches and built CHOLESKY, BARNES, and FMM twice without creating `bin/`.
Mock gem5 commands verified bin-roi selection, two-core forwarding, the CHOLESKY
filename argument, and BARNES/FMM stdin paths. Existing patches are byte-for-byte
unchanged and GAP has no changes. Shell syntax and whitespace checks passed.
No gem5 simulations were run.

Batch 3 completes the remaining targets in this checkout: RADIOSITY, RAYTRACE,
VOLREND, and VOLREND-NPL (`volrend-no_print_lock`). Independent patches preserve
all previous apps, GAP, and the shared ENABLE_ROI macros. Only worker 0 issues
the m5 ops. Without ENABLE_ROI the shared macros remain no-ops.

RADIOSITY (batch mode only): measure convergence/ray gathering/refinement and
final vertex averaging/normalization. Global storage, visibility setup, queue
initialization/assignment, and the initial model/BSP task phase are setup.
Model construction performs initial refinement too: it cannot be separated
cleanly from loading, so that initial refinement is deliberately excluded.
Reset follows `init_modeling_tasks` and its first `process_tasks` drain; a
barrier gathers every worker there, thread 0 resets, and a second barrier
releases convergence. After the final normalization task drain, another barrier
waits for every worker before thread 0 dumps; a following barrier holds timing
statistics, return, display and other reporting until after the dump. Existing
queue termination barriers remain intact. Interactive GUI callbacks are not
instrumented: use `-batch` for ROI runs.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh RADIOSITY
./run_benchmark.sh --suite splash4 --benchmark RADIOSITY --roi --cores 2 \
  --args -batch -p 2 -ae 5000 -en 0.05
```

This uses the built-in test scene (no external input). Area epsilon 5000 and
energy threshold 0.05 make a small functional workload with coarser refinement
and convergence than the default benchmark. It is not a performance reference.

RADIOSITY validation: static ROI build and native two-worker batch runs with
ROI disabled and m5 logging stubs passed (one reset then one dump). No gem5
simulations were run.

RAYTRACE: measure ray tracing/shading while workers consume and steal jobs.
Scene/geometry loading, frame-buffer and acceleration structure creation,
per-worker work pools and ray stacks are setup. Reset follows the existing
work-pool barrier; the added release barrier prevents any ray work before reset.
An explicit completion barrier waits for every worker to return from RayTrace
(an empty local queue is insufficient), then thread 0 dumps and another barrier
holds worker timing reports. Final image output and global reports are outside.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh RAYTRACE
repo="$PWD"
(cd "$repo/benchmarks/splash4/src/Splash-4/raytrace" && \
 "$repo/run_benchmark.sh" --suite splash4 --benchmark RAYTRACE --roi --cores 2 \
 --args -p2 "$repo/benchmarks/splash4/inputs/raytrace-small.env")
```

The tracked environment is the upstream teapot view reduced to 32x32 pixels;
it uses the existing `inputs/teapot.geo`. Run in the source directory so that
relative geometry path resolves. It writes `raytrace-small.rl` there, outside
the ROI. Native checks used temporary directories with a link to upstream
geometry. Static ROI build and native two-worker runs with ROI disabled and
m5 logging stubs passed (one reset then one dump), producing an image file.

VOLREND: there is no clean single rendering interval across frames, because
frame computation alternates with timing reports and TIFF output. The chosen
compromise is one reset/dump pair per frame, not one whole-run pair. Load_Map,
normals, opacity, octree, image allocation, view selection, image clearing,
initial queue counters, observer transforms, and inverse-Jacobian setup are
outside. Pre_Shade, ray tracing, internal queue rearming, and (in adaptive mode)
interpolation are measured. In Ray_Trace, a barrier gathers all workers after
setup; worker 0 resets and a release barrier prevents early computation. A
common barrier after either rendering path waits for every worker before worker
0 dumps; another barrier holds per-frame timing output and TIFF writes outside.
All existing algorithm barriers remain intact. The build's DIM setting renders
three axes: ROTATE_STEPS=1 gives three frames and three ROI dumps. Use those
explicit dump blocks individually (or aggregate their counters); a later gem5
exit block also contains work after the last dump and is not a frame ROI.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh VOLREND
repo="$PWD"
mkdir -p results/splash4-roi/volrend
cp benchmarks/splash4/src/Splash-4/volrend/inputs/head-scaleddown4.den \
  results/splash4-roi/volrend/head.den
(cd results/splash4-roi/volrend && \
 "$repo/run_benchmark.sh" --suite splash4 --benchmark VOLREND --roi --cores 2 \
 --args 2 head 1)
```

`head-scaleddown4.den` is the smallest bundled volume (about 113 KiB). The
argument is the file prefix `head`, without `.den`. Copying it to the output
directory keeps TIFF writes away from the source dataset. No new volume file
is required. Repeated runs overwrite the generated TIFFs.

VOLREND validation: static ROI build and native two-worker nonadaptive runs
with ROI disabled and m5 logging stubs passed; each produced three nonempty
TIFFs, with three reset/dump pairs in the instrumented run. The optional
adaptive small-input native check with ROI disabled exceeded 60 seconds;
adaptive completion is not validated. The recommended command is nonadaptive,
as in upstream's base workload guidance. No simulations were run.
The same adaptive input also exceeded a 10-second check in a fresh, unmodified
upstream build with no ROI patches applied; this limitation was not fixed here.

VOLREND-NPL (`volrend-no_print_lock`): measure the same per-frame shading,
ray tracing and optional interpolation as VOLREND. Volume preprocessing and
frame/view/initial-queue setup are outside; progress recording, frame printing
and TIFF output follow the dump. A single region across frames would include
those writes, so this variant also uses one ROI per frame. In Ray_Trace, an
entry barrier gathers workers before worker 0 resets and a release barrier
holds computation. A common completion barrier after either rendering path
waits for every worker before worker 0 dumps; another holds progress recording
and output. Existing algorithm barriers and the no-print-lock design stay intact.

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh VOLREND-NPL
repo="$PWD"
mkdir -p results/splash4-roi/volrend-npl
cp benchmarks/splash4/src/Splash-4/volrend-no_print_lock/inputs/head-scaleddown4.den \
  results/splash4-roi/volrend-npl/head.den
(cd results/splash4-roi/volrend-npl && \
 "$repo/run_benchmark.sh" --suite splash4 --benchmark VOLREND-NPL --roi --cores 2 \
 --args 2 head 1)
```

This uses the same smallest bundled volume, two workers and one rotation step
per axis, producing three frames/ROI dumps. The dataset prefix stays short
because upstream stores filenames in a fixed-size buffer. No new volume file
is required. Use nonadaptive mode for the supplied small run; adaptive-mode
completion is not validated.

VOLREND-NPL validation: static ROI build and native two-worker nonadaptive runs
with ROI disabled and m5 logging stubs passed. Three frames produced three
nonempty TIFFs; the instrumented run recorded three alternating reset/dump
pairs. No simulations were run.

Build all batch 3 targets, leaving previously completed binaries untouched:

```sh
ENABLE_ROI=1 GEM5_ROOT="$HOME/gem5" benchmarks/splash4/build.sh \
  RADIOSITY RAYTRACE VOLREND VOLREND-NPL
```

Batch 3 integration validation: all patches applied to a fresh upstream archive;
these four static ROI targets built twice and no `bin/` directory was created.
Mock gem5 invocations checked each binary selection, two-core setting, and
benchmark arguments. Earlier ROI patches remained byte-identical; GAP has no
changes. Shell syntax and whitespace checks passed. No gem5 simulations ran.

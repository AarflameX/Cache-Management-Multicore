The existing gem5 crash logs point to an unchecked pyramid read, not to a
confirmed pointer truncation. No new simulations were run for this investigation.

Evidence from the supplied workspace:

- `results/q_VOLREND.log`: PC 0x407087, read from [r15+r9]. The saved static
  `bin-roi/VOLREND` identifies this as Trace_Ray. The preceding instructions
  convert the three floating-point sample coordinates to 64-bit integers,
  flatten them with the pyramid row sizes, and shift right three bits to
  address the packed bit array. This is the PYR(0,samplez,sampley,samplex) read.
- `results/q_VOLREND-NPL.log`: PC 0x407107 is the equivalent instruction in
  that binary, with the same unmapped address 0x7c0555d53. This is before image
  output; the TIFF writer is not the faulting path.
- Both variants store pyramid addresses in BYTE* arrays and the temporary
  address in BYTE*. NU_MALLOC in pthread.m4 returns void*. Their offsets are
  long, which is 64 bits in this Linux x86-64 LP64 build. No pointer-to-int
  narrowing was found along this path. The int map/pyramid lengths are counts,
  not pointer storage; the supplied volume fits those counts.
- Previously, PYR_ADDRESS formed a pointer from coordinates with no level,
  per-axis, or allocation-length check. Trace_Ray also converted stepped float
  samples to integers without checking range/finiteness. An invalid index can
  therefore cause an arbitrary out-of-bounds read even with an intact pointer.
  The logs lack the register values needed to prove why the index/base was bad.

The defensive fix in `volrend-index.patch` is identical for both variants:

1. Reject stepped samples outside the volume before float-to-long conversion;
   ordered comparisons also reject NaNs and infinities.
2. Replace read-only PYR with a checked inline read: validate the level and all
   three coordinates, compute the offset in size_t, validate allocation length,
   then access the pointer. Out-of-volume reads return the empty occupancy bit.
   The existing write macro and ROI marker locations remain unchanged.

This prevents unchecked pyramid indexing; it does not establish why gem5
produced the original fault or prove that a corrupted base pointer is repaired.
Retesting the original gem5 run is still needed. Bounds checks add work to the
measured rendering path, so its performance should not be compared directly to
an unchecked build as if instrumentation cost were identical.

The builder applies this patch independently of ENABLE_ROI, before ROI patches,
with forward/reverse checks. Both the normal and ROI source builds receive it.
Existing bin/ binaries were not overwritten during validation.

Validation completed:

- Static ROI builds of VOLREND and VOLREND-NPL.
- Native two-worker nonadaptive runs with ROI disabled and with m5 logging
  stubs: three images per variant and three alternating reset/dump pairs.
- All three TIFFs in each variant match unmodified upstream native output
  byte-for-byte for head-scaleddown4.den, two workers, one rotation step per
  axis. Native runs used temporary directories.
- `tests/volrend-index.c` checks valid bit access, per-axis rejection (including
  row wrapping), negative/huge indices, invalid levels, and allocation-length
  rejection against each variant's generated address.h.
- Address/undefined sanitizer builds could not link: the installed compiler
  references missing libasan runtime libraries. No sanitizer success is claimed.

Build the corrected ROI binaries:

```sh
ENABLE_ROI=1 benchmarks/splash4/build.sh VOLREND VOLREND-NPL
```

After building, run the focused native boundary checks:

```sh
for variant in volrend volrend-no_print_lock; do
  gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -I"benchmarks/splash4/src/Splash-4/$variant" \
    benchmarks/splash4/tests/volrend-index.c -o "/tmp/$variant-index-test"
  "/tmp/$variant-index-test"
done
```

Fresh-tree validation also passed: all patches applied to an upstream archive,
both static ROI targets built twice, and no bin/ directory was created there.

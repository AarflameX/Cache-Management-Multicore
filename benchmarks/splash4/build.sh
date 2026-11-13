#!/usr/bin/env bash
# Static pthread/m4 SPLASH-4 build for Linux x86-64 gem5 SE workloads.
set -euo pipefail
suite_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${suite_dir}/src"
compiler="${CC:-gcc}"
for tool in git make m4 "$compiler"; do
    command -v "$tool" >/dev/null || { echo "ERROR: missing tool: $tool" >&2; exit 1; }
done
case "$("$compiler" -dumpmachine)" in
    x86_64*-linux*) ;;
    *) echo 'ERROR: a Linux x86-64 compiler is required' >&2; exit 1 ;;
esac
if [[ ! -e "$source_dir" ]]; then
    git clone https://github.com/OdnetninI/Splash-4.git "$source_dir"
fi
[[ -f "$source_dir/Makefile.config" && -f "$source_dir/pthread.m4" ]] || {
    echo "ERROR: invalid SPLASH-4 checkout: $source_dir" >&2; exit 1;
}
# Upstream invokes m4 -Ulen -Uindex -P with pthread.m4, generating C11
# atomics and pthread code. Keep ATOMIC_BARRIERS enabled in both m4 and C.
output_dir="${suite_dir}/bin"
roi_flags=''
roi_libs=''
case "${ENABLE_ROI:-0}" in
    0) ;;
    1)
        gem5_root="${GEM5_ROOT:-$HOME/gem5}"
        roi_libs="${gem5_root}/util/m5/build/x86/out/libm5.a"
        [[ -f "$roi_libs" && -f "${gem5_root}/include/gem5/m5ops.h" ]] || {
            echo "ERROR: build libm5 first: cd ${gem5_root}/util/m5 && scons build/x86/out/libm5.a" >&2
            exit 1
        }
        for roi_patch in "${suite_dir}/roi.patch" "${suite_dir}"/roi-*.patch; do
            [[ -f "$roi_patch" ]] || continue
            if ! git -C "$source_dir" apply --reverse --check "$roi_patch" 2>/dev/null; then
                git -C "$source_dir" apply --check "$roi_patch"
                git -C "$source_dir" apply "$roi_patch"
            fi
        done
        roi_flags=" -DENABLE_ROI -I${gem5_root}/include"
        output_dir="${suite_dir}/bin-roi"
        ;;
    *) echo 'ERROR: ENABLE_ROI must be 0 or 1' >&2; exit 1 ;;
esac
# Optional target selection also makes small non-ROI rebuilds possible.
for requested in "$@"; do
    case "$requested" in
        FFT|LU-CONT|RADIX|RAYTRACE|RADIOSITY|FMM|BARNES|CHOLESKY|WATER-SPATIAL|WATER-NSQUARED|OCEAN-NOCONT|OCEAN-CONT|LU-NOCONT) ;;
        *) echo "ERROR: unsupported selected target: $requested" >&2; exit 1 ;;
    esac
done
mkdir -p "$output_dir"
# Each benchmark makefile declares its executable name in TARGET.
for makefile in "$source_dir"/Splash-4/*/Makefile; do
    target="$(sed -n 's/^TARGET[[:space:]]*=[[:space:]]*//p' "$makefile")"
    [[ -n "$target" ]] || continue
    if (( $# )); then
        selected=0
        for requested in "$@"; do
            [[ "$target" != "$requested" ]] || selected=1
        done
        (( selected )) || continue
    fi
    if [[ "${ENABLE_ROI:-0}" == 1 ]]; then
        case "$target" in FFT|LU-CONT|RADIX|RAYTRACE|RADIOSITY|FMM|BARNES|CHOLESKY|WATER-SPATIAL|WATER-NSQUARED|OCEAN-NOCONT|OCEAN-CONT|LU-NOCONT) ;; *) continue ;; esac
    fi
    flags='-O2 -pthread -D_XOPEN_SOURCE=500 -D_POSIX_C_SOURCE=200112 -std=c11 -fno-strict-aliasing -D ATOMIC_BARRIERS -march=x86-64 -I./libtiff -I./glibdumb -I./glibps'
    case "$target" in
        VOLREND*)
            # Preserve the bundled legacy libtiff's configuration when
            # overriding CFLAGS, and allow its pre-C99 declarations on GCC 14+.
            flags+=' -DUSE_VARARGS=0 -DUSE_PROTOTYPES=1 -DHAVE_IEEEFP=1 -DCOLORIMETRY_SUPPORT -DJPEG_SUPPORT -DYCBCR_SUPPORT -DCMYK_SUPPORT -DMMAP_SUPPORT -Wno-error=implicit-int -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=int-conversion'
            ;;
    esac
    # Upstream leaf makefiles have executable targets rather than an all target.
    make -B -C "$(dirname -- "$makefile")" -j "${JOBS:-2}" "$target" CC="$compiler" \
        CFLAGS="$flags$roi_flags" \
        LDFLAGS="-static -no-pie -pthread -lm $roi_libs"
    install -m 755 "$(dirname -- "$makefile")/$target" "${output_dir}/$target"
done
echo "Built static SPLASH-4 binaries in ${output_dir}"

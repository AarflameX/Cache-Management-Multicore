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
mkdir -p "${suite_dir}/bin"
# Each benchmark makefile declares its executable name in TARGET.
for makefile in "$source_dir"/Splash-4/*/Makefile; do
    target="$(sed -n 's/^TARGET[[:space:]]*=[[:space:]]*//p' "$makefile")"
    [[ -n "$target" ]] || continue
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
        CFLAGS="$flags" \
        LDFLAGS='-static -no-pie -pthread -lm'
    install -m 755 "$(dirname -- "$makefile")/$target" "${suite_dir}/bin/$target"
done
echo "Built static SPLASH-4 binaries in ${suite_dir}/bin"

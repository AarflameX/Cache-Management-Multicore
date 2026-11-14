#!/usr/bin/env bash
# Build static Linux x86-64 GAP workloads for gem5 SE mode.
set -euo pipefail
suite_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${suite_dir}/src"
for tool in git make "${CXX:-g++}"; do
    command -v "$tool" >/dev/null || { echo "ERROR: missing tool: $tool" >&2; exit 1; }
done
if [[ ! -e "$source_dir" ]]; then
    git clone https://github.com/sbeamer/gapbs.git "$source_dir"
elif [[ ! -f "$source_dir/Makefile" || ! -f "$source_dir/src/bfs.cc" ]]; then
    echo "ERROR: ${source_dir} is not a GAP Benchmark Suite checkout" >&2
    exit 1
fi
kernels=(bfs pr cc sssp bc tc)
if (( $# )); then
    kernels=("$@")
fi
for kernel in "${kernels[@]}"; do
    case "$kernel" in
        bfs|pr|cc|sssp|bc|tc) ;;
        *) echo "ERROR: unsupported GAP kernel: $kernel" >&2; exit 1 ;;
    esac
done
# Keep scheduling identical in native and ROI binaries. Sources are ignored;
# retain this change as a patch, using the ROI patch's repeat-build checks.
if ! git -C "$source_dir" apply --reverse --check "${suite_dir}/chunks.patch" 2>/dev/null; then
    git -C "$source_dir" apply --check "${suite_dir}/chunks.patch"
    git -C "$source_dir" apply "${suite_dir}/chunks.patch"
fi
flags='-std=c++11 -O3 -Wall -fopenmp -static -march=x86-64'
roi_libs=''
output_dir="${suite_dir}/bin"
case "${ENABLE_ROI:-0}" in
    0) ;;
    1)
        gem5_root="${GEM5_ROOT:-$HOME/gem5}"
        roi_libs="${gem5_root}/util/m5/build/x86/out/libm5.a"
        [[ -f "$roi_libs" && -f "${gem5_root}/include/gem5/m5ops.h" ]] || {
            echo "ERROR: build libm5 first: cd ${gem5_root}/util/m5 && scons build/x86/out/libm5.a" >&2
            exit 1
        }
        # Sources are ignored by Git; keep instrumentation in a tracked patch.
        if ! git -C "$source_dir" apply --reverse --check "${suite_dir}/roi.patch" 2>/dev/null; then
            git -C "$source_dir" apply --check "${suite_dir}/roi.patch"
            git -C "$source_dir" apply "${suite_dir}/roi.patch"
        fi
        flags+=" -DENABLE_ROI -I${gem5_root}/include"
        output_dir="${suite_dir}/bin-roi"
        ;;
    *) echo 'ERROR: ENABLE_ROI must be 0 or 1' >&2; exit 1 ;;
esac
# Force rebuilding so existing dynamically linked binaries cannot be reused.
make -B -C "$source_dir" -j "${JOBS:-2}" "${kernels[@]}" \
    CXX="${CXX:-g++}" \
    CXX_FLAGS="$flags" ROI_LIBS="$roi_libs"
mkdir -p "$output_dir"
for kernel in "${kernels[@]}"; do
    install -m 755 "${source_dir}/${kernel}" "${output_dir}/${kernel}"
done
echo "Built static GAP binaries in ${output_dir}"

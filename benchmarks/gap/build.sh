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
# Force rebuilding so existing dynamically linked binaries cannot be reused.
make -B -C "$source_dir" -j "${JOBS:-2}" "${kernels[@]}" \
    CXX="${CXX:-g++}" \
    CXX_FLAGS='-std=c++11 -O3 -Wall -fopenmp -static -march=x86-64'
mkdir -p "${suite_dir}/bin"
for kernel in "${kernels[@]}"; do
    install -m 755 "${source_dir}/${kernel}" "${suite_dir}/bin/${kernel}"
done
echo "Built static GAP binaries in ${suite_dir}/bin"

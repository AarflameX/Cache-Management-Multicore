#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RODINIA_DIR="${REPO_ROOT}/benchmarks/rodinia_3.1/openmp"
GEM5_ROOT="${1:-$(find "${REPO_ROOT}/.." -maxdepth 1 -type d -name 'gem5-*' | head -n1)}"

if [ -z "${GEM5_ROOT}" ] || [ ! -d "${GEM5_ROOT}" ]; then
    echo "ERROR: could not locate a gem5 checkout." >&2
    exit 1
fi

echo "Repo root:   ${REPO_ROOT}"
echo "Rodinia:     ${RODINIA_DIR}"
echo "gem5 root:   ${GEM5_ROOT}"

M5_DIR="${GEM5_ROOT}/util/m5"
if [ ! -f "${M5_DIR}/build/x86/out/m5" ]; then
    echo "Building gem5 m5 utility..."
    (cd "${M5_DIR}" && scons build/x86/out/m5)
else
    echo "m5 utility already built, skipping."
fi

declare -A BUILD_TARGET=(
    ["bfs"]="bfs"
    ["hotspot"]="hotspot"
    ["nw"]="needle"
    ["lud"]="lud_omp"
)

EXCLUDE=("mummergpu")

FAILED=()
build_dir() {
    local dir="$1"
    local label="$2"
    local target="${BUILD_TARGET[${label}]:-}"
    echo "=== Building ${label} ${target:+(target: $target)} ==="
    if ! (cd "${dir}" && make ${target} \
            CFLAGS="-fopenmp -static -O2" \
            CXXFLAGS="-fopenmp -static -O2" \
            LDFLAGS="-fopenmp -static"); then
        echo "!!! FAILED: ${label}"
        FAILED+=("${label}")
    fi
}

for dir in "${RODINIA_DIR}"/*/; do
    name="$(basename "${dir}")"
    if [[ " ${EXCLUDE[*]} " == *" ${name} "* ]]; then
        echo "!!! EXCLUDED: ${name}"
        continue
    fi
    if [ -f "${dir}/Makefile" ]; then
        build_dir "${dir}" "${name}"
    else
        echo "!!! SKIPPED: ${name} (no Makefile found)"
    fi
done

echo
echo "==================== Build summary ===================="
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "All benchmarks built successfully."
else
    echo "Failed benchmarks:"
    for f in "${FAILED[@]}"; do
        echo "  - ${f}"
    done
    exit 1
fi

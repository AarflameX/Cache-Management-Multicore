#!/usr/bin/env bash
# Builds all SPLASH-3 benchmarks for use with gem5 SE mode.
#
# Usage:
#   ./scripts/build_splash3.sh [path-to-gem5-root]
#
# If path-to-gem5-root is omitted, this script assumes gem5 lives as a
# sibling directory of the repo root (matching the team's current layout:
# ~/Gem5Workspace/{Cache-Management-Multicore, gem5-25.1.0.1, m5out}).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLASH_DIR="${REPO_ROOT}/benchmarks/splash-3/codes"
GEM5_ROOT="${1:-$(find "${REPO_ROOT}/.." -maxdepth 1 -type d -name 'gem5-*' | head -n1)}"

if [ -z "${GEM5_ROOT}" ] || [ ! -d "${GEM5_ROOT}" ]; then
    echo "ERROR: could not locate a gem5 checkout." >&2
    echo "Pass it explicitly: ./scripts/build_splash3.sh /path/to/gem5" >&2
    exit 1
fi

echo "Repo root:  ${REPO_ROOT}"
echo "SPLASH-3:   ${SPLASH_DIR}"
echo "gem5 root:  ${GEM5_ROOT}"
export GEM5_ROOT

# --- 1. Set BASEDIR in Makefile.config to this checkout's absolute path ---
CONFIG_FILE="${SPLASH_DIR}/Makefile.config"
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "ERROR: ${CONFIG_FILE} not found. Did benchmarks/splash-3/codes get committed correctly?" >&2
    exit 1
fi
sed -i.bak "s|^BASEDIR.*|BASEDIR = ${SPLASH_DIR}|" "${CONFIG_FILE}"
echo "Set BASEDIR = ${SPLASH_DIR}"

# --- 2. Build gem5's m5 utility (needed for m5_reset_stats/m5_dump_stats) ---
M5_DIR="${GEM5_ROOT}/util/m5"
if [ ! -f "${M5_DIR}/build/x86/out/m5" ]; then
    echo "Building gem5 m5 utility..."
    (cd "${M5_DIR}" && scons build/x86/out/m5)
else
    echo "m5 utility already built, skipping."
fi

# --- 3. Build each app and kernel individually, reporting pass/fail ---
# Some benchmarks (e.g. ocean, lu) don't have a Makefile directly in their
# top-level folder -- they split into build variants one directory deeper
# (contiguous_partitions/, non_contiguous_partitions/, etc). Handle both
# layouts without hardcoding which benchmarks happen to nest.
FAILED=()
build_dir() {
    local dir="$1"
    local label="$2"
    echo "=== Building ${label} ==="
    if ! (cd "${dir}" && make); then
        echo "!!! FAILED: ${label}"
        FAILED+=("${label}")
    fi
}

for dir in "${SPLASH_DIR}"/apps/*/ "${SPLASH_DIR}"/kernels/*/; do
    name="$(basename "${dir}")"
    if [ -f "${dir}/Makefile" ]; then
        build_dir "${dir}" "${name}"
    else
        found_variant=0
        for subdir in "${dir}"*/; do
            if [ -f "${subdir}/Makefile" ]; then
                found_variant=1
                build_dir "${subdir}" "${name}/$(basename "${subdir}")"
            fi
        done
        if [ "${found_variant}" -eq 0 ]; then
            echo "!!! FAILED: ${name} (no Makefile found at top level or one level deep)"
            FAILED+=("${name}")
        fi
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

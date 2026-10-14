#!/usr/bin/env bash
# Build static SPLASH-4 binaries for gem5's Linux x86-64 SE workloads.
# Usage from any working directory: bash /path/to/repo/scripts/build_splash4.sh [all|lu]
# Requires Bash, GNU make, GNU m4, and GCC with static libc/libm/libpthread.
set -euo pipefail

usage() {
    echo "Usage: bash $0 [all|lu]"
    echo "  all  Build the entire SPLASH-4 suite (default)."
    echo "  lu   Build only LU with contiguous blocks (LU-CONT)."
    echo "Set CC to select a Linux x86-64 GCC compiler."
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
TARGET="${1:-all}"
if [[ $# -gt 1 || ( "$TARGET" != "all" && "$TARGET" != "lu" ) ]]; then
    usage >&2
    exit 2
fi

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SPLASH_DIR="${REPO_ROOT}/benchmarks/Splash-4"
SPLASH_CC="${CC:-gcc}"

for tool in make m4 "$SPLASH_CC"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: required tool '$tool' was not found." >&2
        echo "On Ubuntu/WSL: sudo apt-get install build-essential m4" >&2
        exit 1
    fi
done
if ! make --version | head -n 1 | grep -q 'GNU Make'; then
    echo "ERROR: GNU make is required." >&2
    exit 1
fi
if ! m4 --version | head -n 1 | grep -q 'GNU M4'; then
    echo "ERROR: GNU m4 is required." >&2
    exit 1
fi
if [[ ! -f "${SPLASH_DIR}/Makefile.gem5" || ! -f "${SPLASH_DIR}/pthread.m4" ]]; then
    echo "ERROR: expected the SPLASH-4 sources in ${SPLASH_DIR}." >&2
    exit 1
fi
case "$("$SPLASH_CC" -dumpmachine)" in
    x86_64*-linux*) ;;
    *)
        echo "ERROR: gem5's X86 SE workload requires a Linux x86-64 compiler." >&2
        echo "Use Linux/WSL on x86-64, or set CC to a Linux x86-64 GCC cross compiler." >&2
        exit 1
        ;;
esac

# Check static system libraries before spending time on the suite.
BUILD_CHECK_DIR="$(mktemp -d)"
trap 'rm -rf -- "$BUILD_CHECK_DIR"' EXIT
if ! "$SPLASH_CC" -x c - -o "${BUILD_CHECK_DIR}/check" \
        -std=c11 -march=x86-64 -static -no-pie -pthread -lm <<'EOF'
#include <pthread.h>
#include <math.h>
int main(void) { pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    volatile double value = 2.0;
    return pthread_mutex_lock(&lock) || pthread_mutex_unlock(&lock)
        || sqrt(value) <= 0.0; }
EOF
then
    echo "ERROR: could not link a static Linux x86-64 program." >&2
    echo "Install your compiler's static libc, libm and pthread development libraries." >&2
    echo "On Ubuntu/WSL: sudo apt-get install build-essential libc6-dev m4" >&2
    exit 1
fi

echo "SPLASH-4: ${SPLASH_DIR}"
echo "Compiler: ${SPLASH_CC}"
echo "Target:   ${TARGET}"
if ! make -k -C "$SPLASH_DIR" -f Makefile.gem5 "$TARGET" CC="$SPLASH_CC"; then
    echo "ERROR: SPLASH-4 build failed; see the make errors above." >&2
    exit 1
fi
echo "SPLASH-4 build completed."
echo "Contiguous LU: ${SPLASH_DIR}/Splash-4/lu-contiguous_blocks/LU-CONT"

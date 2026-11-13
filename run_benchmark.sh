#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: ./run_benchmark.sh --suite <suite> --benchmark <binary> [--cores <N>] [--args <arguments...>]

--cores defaults to 2 and must be a positive multiple of 2.
--input <file> supplies benchmark stdin (before --args).
--roi selects GAP or SPLASH-4 binaries from bin-roi/ (built with ENABLE_ROI=1).
--args must come last; all remaining tokens are passed to the benchmark.
A single quoted --args string is parsed using shell-style quoting (no expansion).
GEM5_BIN overrides the default executable at ~/gem5/build/X86/gem5.opt.
HELP
}
die() { echo "ERROR: $*" >&2; exit 2; }
suite=''
benchmark=''
cores=2
roi=0
input_file=''
benchmark_args=()
while (( $# )); do
    case "$1" in
        --suite|--benchmark|--cores|--input)
            (( $# >= 2 )) || die "$1 requires a value"
            [[ -n "$2" && "$2" != --* ]] || die "$1 requires a value"
            case "$1" in
                --suite) suite="$2" ;;
                --benchmark) benchmark="$2" ;;
                --cores) cores="$2" ;;
                --input) input_file="$2" ;;
            esac
            shift 2
            ;;
        --roi) roi=1; shift ;;
        --args) shift; benchmark_args=("$@"); break ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
done
[[ -n "$suite" ]] || die "--suite is required"
[[ -n "$benchmark" ]] || die "--benchmark is required"
for name in "$suite" "$benchmark"; do
    [[ "$name" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.+-]*$ ]] || die "invalid suite or benchmark name: $name"
done
# Validate as text to avoid overflow for large integer inputs.
[[ "$cores" =~ ^[0-9]+$ && "$cores" =~ [1-9] && "$cores" =~ [02468]$ ]] || die "--cores must be a positive multiple of 2"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
binary_dir=bin
if (( roi )); then
    [[ "$suite" == gap || "$suite" == splash4 ]] || die '--roi supports GAP and SPLASH-4'
    if [[ "$suite" == splash4 ]]; then
        case "$benchmark" in FFT|LU-CONT|RADIX|VOLREND-NPL|VOLREND|RAYTRACE|RADIOSITY|FMM|BARNES|CHOLESKY|WATER-SPATIAL|WATER-NSQUARED|OCEAN-NOCONT|OCEAN-CONT|LU-NOCONT) ;; *) die '--roi: unsupported SPLASH-4 benchmark' ;; esac
    fi
    binary_dir=bin-roi
fi
binary="${repo_root}/benchmarks/${suite}/${binary_dir}/${benchmark}"
GEM5_BIN="${GEM5_BIN:-$HOME/gem5/build/X86/gem5.opt}"
[[ -f "$binary" && -x "$binary" ]] || die "benchmark not found or not executable: $binary; run benchmarks/${suite}/build.sh first"
[[ -f "$GEM5_BIN" && -x "$GEM5_BIN" ]] || die "gem5 not found or not executable: $GEM5_BIN; set GEM5_BIN to your gem5 executable"
input_options=()
if [[ -n "$input_file" ]]; then
    [[ -f "$input_file" && -r "$input_file" ]] || die "input file not readable: $input_file"
    input_file="$(cd -- "$(dirname -- "$input_file")" && pwd)/$(basename -- "$input_file")"
    input_options=(--input "$input_file")
fi
exec "$GEM5_BIN" "${repo_root}/mesi_two_level_se_multi.py" \
    --binary "$binary" --cores "$cores" "${input_options[@]}" --args "${benchmark_args[@]}"

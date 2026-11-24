#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( $# > 1 )); then
    echo "Usage: $0 [gem5-binary]" >&2
    exit 2
fi
gem5=$(realpath -- "${1:-${GEM5_BIN:-$HOME/gem5/build/X86/gem5.opt}}")
bench="$repo/benchmarks/gap/bin-roi/bfs"
printf 'gem5 commit: '
python3 "$repo/scripts/run_provenance.py" commit "$gem5"
info=$("$gem5" --build-info)
printf '%s\n' "$info"
if ! grep -Eq '^[[:space:]]*USE_X86_ISA = True$' <<< "$info" ||
    ! grep -Eq '^[[:space:]]*(RUBY_PROTOCOL_MESI_Two_Level = True|PROTOCOL = MESI_Two_Level)$' <<< "$info"; then
    echo 'ERROR: gem5 build must support X86 and MESI_Two_Level' >&2
    exit 1
fi
sha256sum -- "$gem5" "$bench"
work=$(mktemp -d)
trap 'rm -r -- "$work"' EXIT
printf 'gap|bfs|-g 10 -n 1|1|120\n' > "$work/smoke.conf"
if ! "$repo/run_experiment.sh" --gem5-bin "$gem5" --conf "$work/smoke.conf" \
    --results "$work" --variant smoke --cores 2 --jobs 1; then
    if [[ -f "$work/smoke/gap_bfs_c2/run.log" ]]; then
        cat "$work/smoke/gap_bfs_c2/run.log" >&2
    fi
    exit 1
fi
python3 "$repo/scripts/check_cache_indexing.py" "$work/smoke/gap_bfs_c2" --cores 2
python3 - "$work/smoke/summary.csv" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="") as summary:
    print("simSeconds:", next(csv.DictReader(summary))["simSeconds"])
PY

#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( $# < 1 || $# > 2 )) || [[ ! "$1" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.+-]*$ ]] ||
    [[ -n "${2:-}" && "$2" != --dry-run ]]; then
    echo "Usage: $0 <runner> [--dry-run]" >&2
    exit 2
fi
runner=$1
variant="xcheck-$runner"
gem5="${GEM5_BIN:-$HOME/gem5/build/X86/gem5.opt}"
cd -- "$repo"
conf=$(mktemp)
trap 'rm -f -- "$conf"' EXIT
cat > "$conf" <<'CONF'
gap|bfs|-g 10 -n 1|1|5400
splash4|OCEAN-CONT|-p{cores} -n34|1|5400
splash4|FFT|-p{cores} -m10|1|5400
CONF
options=(--conf "$conf" --variant "$variant" --gem5-bin "$gem5"
         --cores 4 --jobs 1 --seed 5489 --runner "$runner")
if [[ ${2:-} == --dry-run ]]; then
    "$repo/run_experiment.sh" "${options[@]}" --dry-run
    exit 0
fi
"$repo/run_experiment.sh" "${options[@]}"
for job in gap_bfs_c4 splash4_OCEAN-CONT_c4 splash4_FFT_c4; do
    # Each job has one ROI dump followed by a final exit dump.
    digest=$(awk '
        /Begin Simulation Statistics/ { roi = 1 }
        roi && $1 !~ /^host/ { print }
        /End Simulation Statistics/ && roi { complete = 1; exit }
        END { if (!complete) exit 1 }
    ' "results/$variant/$job/stats.txt" | sha256sum)
    printf '%s  %s\n' "${digest%% *}" "$job"
done

#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
gem5=${GEM5_BIN:-$HOME/gem5/build/X86/gem5.opt}
work=$(mktemp -d)
trap 'rm -r -- "$work"' EXIT
for stride in 64 16384; do
    cc -nostdlib -static -no-pie -Wl,--build-id=none -DSTRIDE="$stride" \
        "$repo/tests/cache_index_probe.S" -o "$work/probe"
    "$gem5" -d "$work/out" "$repo/mesi_two_level_se_multi.py" --cores 4 --binary "$work/probe"
    python3 "$repo/scripts/check_cache_indexing.py" "$work/out" --cores 4
    prefix=board.cache_hierarchy.ruby_system.l1_controllers0.L1Dcache.m_demand_
    hits=$(awk -v key="${prefix}hits" '$1 == key { print $2 }' "$work/out/stats.txt")
    misses=$(awk -v key="${prefix}misses" '$1 == key { print $2 }' "$work/out/stats.txt")
    expected='9/3'
    if [[ $stride == 16384 ]]; then expected='0/12'; fi
    echo "Stride $stride bytes: $hits/$misses L1D hits/misses (expected $expected)"
    [[ "$hits/$misses" == "$expected" ]]
done

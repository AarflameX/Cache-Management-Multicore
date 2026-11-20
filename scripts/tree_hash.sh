#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
unset CDPATH

if (( $# < 1 || $# > 2 )); then
    echo "Usage: $0 <gem5_root> [listfile]" >&2
    exit 2
fi

root=$1
[[ $root = /* ]] || root=$PWD/$root
directories=(src configs site_scons build_opts)
for directory in "${directories[@]}"; do
    if [[ ! -d "$root/$directory" || -L "$root/$directory" ]]; then
        printf 'ERROR: GEM5_ROOT %s requires a directory at %s\n' "$root" "$directory" >&2
        exit 1
    fi
done
if [[ ! -f "$root/SConstruct" || -L "$root/SConstruct" ]]; then
    printf 'ERROR: GEM5_ROOT %s requires a regular file at SConstruct\n' "$root" >&2
    exit 1
fi

manifest=$(mktemp)
trap 'rm -f -- "$manifest"' EXIT
(
    cd -- "$root"
    find "${directories[@]}" SConstruct \
        -type d -name __pycache__ -prune -o \
        -type f ! -name '*.pyc' ! -path src/mem/slicc/parser.out \
        ! -path src/mem/slicc/parsetab.py -print0 |
        sort -z |
        xargs -0 -r sha256sum --
) > "$manifest"

if (( $# == 2 )); then
    cat -- "$manifest" > "$2"
fi
digest=$(sha256sum < "$manifest")
printf 'tree_sha256 %s\nfiles %s\n' "${digest%% *}" "$(wc -l < "$manifest")"

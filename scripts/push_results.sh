#!/usr/bin/env bash
set -euo pipefail
if (( $# != 1 )) || [[ -z "$1" ]]; then
    echo "Usage: $0 <name>" >&2
    exit 2
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
branch="results/$1"
git check-ref-format --branch "$branch" >/dev/null
check_worktree() {
    git status --porcelain=v1 -z --no-renames --untracked-files=all |
        python3 -c '
import sys

outside = [entry[3:] for entry in sys.stdin.buffer.read().split(b"\0")
           if entry and not entry[3:].startswith(b"data/")]
if outside:
    for path in outside:
        print(f"ERROR: modified outside data/: {path!r}", file=sys.stderr)
    sys.exit(1)
'
}
check_worktree
remote_exists=0
if git ls-remote --exit-code --heads origin "refs/heads/$branch" >/dev/null; then
    remote_exists=1
elif [[ $? != 2 ]]; then
    exit 1
fi
if git show-ref --verify --quiet "refs/heads/$branch"; then
    git switch "$branch"
elif (( remote_exists )); then
    git fetch origin "refs/heads/$branch"
    git switch -c "$branch" FETCH_HEAD
else
    git switch -c "$branch"
fi
if (( remote_exists )); then
    git pull --rebase --autostash origin "$branch"
fi
check_worktree
git add -- data/
if ! git diff --cached --quiet; then
    git commit -m "Add results for $1"
fi
git push -u origin "$branch"

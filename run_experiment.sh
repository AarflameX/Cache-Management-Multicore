#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
self="$repo/run_experiment.sh"

# run_benchmark.sh execs GEM5_BIN. This adapter inserts gem5's private outdir
# and config flags before --args, preserving the existing workload environment.
if [[ ${EXPERIMENT_GEM5_ADAPTER:-0} == 1 ]]; then
    exec python3 - "$@" <<'PY'
import os, shlex, sys
args = sys.argv[1:]
index = args.index('--args') if '--args' in args else len(args)
args[index:index] = shlex.split(os.environ['EXPERIMENT_EXTRA'])
os.execv(os.environ['EXPERIMENT_GEM5'], [os.environ['EXPERIMENT_GEM5'],
         '--outdir=' + os.environ['EXPERIMENT_OUT'], *args])
PY
fi

die() { echo "ERROR: $*" >&2; exit 2; }

if [[ ${1:-} == --worker ]]; then
    shift
    suite=$1 benchmark=$2 args=$3 roi=$4 limit=$5 core=$6
    name="${suite}_${benchmark}_c${core}"
    out="$EXPERIMENT_BASE/$name"
    status="$EXPERIMENT_STATE/$name.status"
    mkdir -p "$out"
    if [[ -f "$out/stats.txt" && -f "$out/DONE" && ! -f "$out/FAILED" ]]; then
        echo skipped > "$status"
        echo "SKIP $name"
        exit 0
    fi
    rm -f -- "$out/DONE" "$out/FAILED" "$out/stats.txt" "$out/run.json"
    pgid=''
    watchdog=''
    finish_metadata() {
        [[ -f "$out/run.json" && -n ${EXPERIMENT_STARTED_MONO:-} ]] || return 0
        python3 - "$out/run.json" <<'PYMETA'
import json, os, pathlib, sys, time
path = pathlib.Path(sys.argv[1])
meta = json.loads(path.read_text())
meta['wall_seconds'] = round(time.monotonic() - float(os.environ['EXPERIMENT_STARTED_MONO']), 6)
temporary = path.with_suffix('.json.tmp')
temporary.write_text(json.dumps(meta, indent=2) + '\n')
temporary.replace(path)
PYMETA
    }
    fail() {
        finish_metadata
        rm -f -- "$out/DONE"
        printf '%s\n' "$*" > "$out/FAILED"
        echo failed > "$status"
        echo "FAIL $name: $*"
    }
    stop_group() {
        if [[ -n "$pgid" ]]; then
            kill -TERM -- "-$pgid" 2>/dev/null || true
            kill -KILL -- "-$pgid" 2>/dev/null || true
        fi
        if [[ -n "$watchdog" ]]; then
            kill "$watchdog" 2>/dev/null || true
            wait "$watchdog" 2>/dev/null || true
        fi
    }
    interrupted() {
        trap '' INT TERM HUP
        stop_group
        fail 'interrupted'
        exit 0
    }
    trap interrupted INT TERM HUP
    trap 'rm -f -- "$EXPERIMENT_STATE/$name.worker" "$EXPERIMENT_STATE/$name.group"' EXIT
    echo "$$" > "$EXPERIMENT_STATE/$name.worker"
    [[ ! -f "$EXPERIMENT_STATE/CANCELLED" ]] || interrupted
    export EXPERIMENT_STARTED_MONO
    EXPERIMENT_STARTED_MONO=$(python3 -c 'import time; print(time.monotonic())')
    # Prepare private stdin/data copies and tokenize args without evaluating shell code.
    if ! python3 - "$repo" "$out" "$suite" "$benchmark" "$args" "$roi" "$core" "$EXPERIMENT_VARIANT" <<'PY' > "$out/command.nul" 2> "$out/run.log"
import datetime, json, os, pathlib, shlex, shutil, sys
repo, out, suite, bench, text, roi, core, variant = sys.argv[1:]
root, run = pathlib.Path(repo), pathlib.Path(out)
resolved_args = text.replace('{cores}', core).replace('{repo}', repo)
meta = dict(suite=suite, benchmark=bench, cores=int(core), variant=variant, roi=int(roi),
            gem5_bin=os.environ['EXPERIMENT_GEM5'], gem5_sha256=os.environ['EXPERIMENT_GEM5_SHA256'],
            repo_commit=os.environ['EXPERIMENT_REPO_COMMIT'],
            repo_dirty=os.environ['EXPERIMENT_REPO_DIRTY'] == '1',
            args=resolved_args, extra_args=os.environ['EXPERIMENT_EXTRA'],
            start_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(), wall_seconds=None)
(run / 'run.json').write_text(json.dumps(meta, indent=2) + '\n')
tokens = shlex.split(resolved_args)
command = [str(root / 'run_benchmark.sh'), '--suite', suite, '--benchmark', bench, '--cores', core]
if roi == '1':
    command.append('--roi')
if '<' in tokens:
    index = tokens.index('<')
    if index != len(tokens) - 2:
        raise ValueError("stdin must be specified as a final '< file'")
    source = pathlib.Path(tokens[index + 1])
    if not source.is_absolute():
        source = root / source
    data = source.read_text()
    if bench in ('WATER-NSQUARED', 'WATER-SPATIAL'):
        fields = data.split()
        fields[8] = core
        data = ' '.join(fields) + '\n'
    elif bench in ('BARNES', 'FMM'):
        lines = data.splitlines()
        lines[11 if bench == 'BARNES' else 4] = core
        data = '\n'.join(lines) + '\n'
    (run / 'stdin.in').write_text(data)
    command += ['--input', str(run / 'stdin.in')]
    del tokens[index:]
source_names = {'WATER-NSQUARED': 'water-nsquared', 'WATER-SPATIAL': 'water-spatial',
                'VOLREND': 'volrend', 'VOLREND-NPL': 'volrend-no_print_lock'}
if bench in source_names:
    source = root / 'benchmarks/splash4/src/Splash-4' / source_names[bench]
    if bench.startswith('WATER-'):
        shutil.copyfile(source / 'random.in', run / 'random.in')
    else:
        shutil.copyfile(source / 'inputs/head-scaleddown4.den', run / 'head.den')
if bench == 'RAYTRACE':
    (run / 'inputs').mkdir(exist_ok=True)
    shutil.copyfile(root / 'benchmarks/splash4/src/Splash-4/raytrace/inputs/teapot.geo',
                    run / 'inputs/teapot.geo')
command += ['--args', *tokens]
sys.stdout.buffer.write(b'\0'.join(x.encode() for x in command) + b'\0')
PY
    then
        fail 'input/argument preparation failed; see run.log'
        exit 0
    fi
    mapfile -d '' -t command < "$out/command.nul"
    echo "RUN $name (timeout ${limit}s)"
    cd -- "$out"
    # setsid makes $! the session/process-group leader. The watchdog kills the
    # entire group, even if a shell or gem5 child ignores normal termination.
    [[ ! -f "$EXPERIMENT_STATE/CANCELLED" ]] || interrupted
    EXPERIMENT_GEM5_ADAPTER=1 EXPERIMENT_OUT="$out" GEM5_BIN="$self" \
        setsid "${command[@]}" >> run.log 2>&1 &
    pgid=$!
    echo "$pgid" > "$EXPERIMENT_STATE/$name.group"
    [[ ! -f "$EXPERIMENT_STATE/CANCELLED" ]] || interrupted
    (
        trap 'exit 0' TERM INT HUP
        # read -t on a private FIFO avoids leaving a long-lived sleep child.
        read -r -t "$limit" -u 9 || true
        echo timeout > "$EXPERIMENT_STATE/$name.timeout"
        kill -TERM -- "-$pgid" 2>/dev/null || true
        read -r -t 2 -u 9 || true
        kill -KILL -- "-$pgid" 2>/dev/null || true
    ) &
    watchdog=$!
    code=0
    wait "$pgid" || code=$?
    stop_group
    rm -f -- "$EXPERIMENT_STATE/$name.group"
    finish_metadata
    if [[ -f "$EXPERIMENT_STATE/$name.timeout" ]]; then
        fail "timeout after ${limit}s"
    elif (( code != 0 )); then
        reason=$(tail -n 1 run.log)
        fail "exit status $code: $reason (see run.log)"
    elif ! python3 "$repo/parse_stats.py" --validate "$out" >> run.log 2>&1; then
        reason=$(tail -n 1 run.log)
        fail "statistics parsing failed: $reason"
    else
        touch DONE
        echo done > "$status"
        echo "DONE $name"
    fi
    rm -f -- "$EXPERIMENT_STATE/$name.worker"
    exit 0
fi

cores='2 4 8'
variant=baseline
extra=''
gem5="$HOME/gem5/build/X86/gem5.opt"
jobs=4
conf="$repo/experiments.conf"
filter='.*'
results=results
dry=0
while (( $# )); do
    case "$1" in
        --cores|--variant|--extra-args|--gem5-bin|--jobs|--conf|--filter|--results)
            (( $# >= 2 )) || die "$1 requires a value"
            case "$1" in
                --cores) cores=$2 ;; --variant) variant=$2 ;; --extra-args) extra=$2 ;;
                --gem5-bin) gem5=$2 ;; --jobs) jobs=$2 ;; --conf) conf=$2 ;;
                --filter) filter=$2 ;; --results) results=$2 ;;
            esac
            shift 2 ;;
        --dry-run) dry=1; shift ;;
        -h|--help)
            echo 'Usage: ./run_experiment.sh [--cores "2 4 8"] [--variant NAME]'
            echo '  [--extra-args "..."] [--gem5-bin PATH] [--jobs N] [--conf FILE]'
            echo '  [--filter REGEX] [--dry-run] [--results DIR]'
            exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
done
[[ "$variant" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.+-]*$ && "$variant" != .. ]] || die 'invalid variant name'
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || die '--jobs must be a positive integer'
read -r -a core_list <<< "$cores"
(( ${#core_list[@]} )) || die '--cores must not be empty'
declare -A core_seen=()
for core in "${core_list[@]}"; do
    [[ "$core" =~ ^[1-9][0-9]*$ && "$core" =~ [02468]$ ]] || die 'core counts must be positive even integers'
    [[ ! ${core_seen[$core]+yes} ]] || die "duplicate core count: $core"
    core_seen[$core]=1
done
[[ -f "$conf" ]] || die "configuration not found: $conf"
if [[ '' =~ $filter ]]; then :; elif (( $? == 2 )); then die 'invalid filter regex'; fi
# Check all conf records and quoting before scheduling any jobs.
records=()
declare -A seen=()
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    [[ "${line//[^|]/}" == '||||' ]] || die "expected five conf fields: $line"
    IFS='|' read -r suite benchmark args roi limit rest <<< "$line"
    [[ "$suite" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.+-]*$ && "$benchmark" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.+-]*$ ]] || die "invalid suite/benchmark: $line"
    [[ "$roi" =~ ^[01]$ && "$limit" =~ ^[1-9][0-9]*$ && -z "$rest" ]] || die "invalid record: $line"
    [[ ! ${seen[$suite/$benchmark]+yes} ]] || die "duplicate benchmark: $suite/$benchmark"
    seen[$suite/$benchmark]=1
    python3 -c 'import shlex,sys; shlex.split(sys.argv[1])' "$args" || die "invalid args: $line"
    if [[ "$benchmark" =~ $filter ]]; then
        records+=("$suite" "$benchmark" "$args" "$roi" "$limit")
    fi
done < "$conf"
python3 -c 'import shlex,sys; shlex.split(sys.argv[1])' "$extra" || die 'invalid --extra-args'
gem5=$(realpath -m -- "$gem5")
base=$(realpath -m -- "$results/$variant")
if (( dry )); then
    for (( i=0; i<${#records[@]}; i+=5 )); do
        for core in "${core_list[@]}"; do
            suite=${records[i]} benchmark=${records[i+1]}
            out="$base/${suite}_${benchmark}_c$core"
            args=${records[i+2]//\{cores\}/$core}
            args=${args//\{repo\}/$repo}
            python3 - "$out" "${records[i+4]}" "$gem5" "$repo" "$suite" "$benchmark" "$core" "${records[i+3]}" "$args" "$extra" <<'PYDRY'
import shlex, sys
out, limit, gem5, repo, suite, bench, core, roi, args, extra = sys.argv[1:]
tokens = shlex.split(args)
command = [repo + '/run_benchmark.sh', '--suite', suite, '--benchmark', bench, '--cores', core]
if roi == '1':
    command += ['--roi']
if '<' in tokens:
    index = tokens.index('<')
    command += ['--input', out + '/stdin.in']
    del tokens[index:]
command += ['--args', *tokens]
env = ['env', 'EXPERIMENT_GEM5_ADAPTER=1', 'EXPERIMENT_OUT=' + out,
       'EXPERIMENT_GEM5=' + gem5, 'EXPERIMENT_EXTRA=' + extra,
       'GEM5_BIN=' + repo + '/run_experiment.sh']
print(f'# outdir={out}; timeout={limit}s; stage private input/data files here')
print('(cd ' + shlex.quote(out) + ' && ' + shlex.join(env + ['setsid'] + command) + ')')
PYDRY
        done
    done
    exit 0
fi
for utility in setsid xargs flock python3; do command -v "$utility" >/dev/null || die "$utility is required"; done
[[ -x "$gem5" ]] || die "gem5 is not executable: $gem5"
# Hash the executable once per sweep, not once per parallel worker.
EXPERIMENT_GEM5_SHA256=$(python3 - "$gem5" <<'PYHASH'
import hashlib, sys
hash_value = hashlib.sha256()
with open(sys.argv[1], 'rb') as executable:
    for chunk in iter(lambda: executable.read(1024 * 1024), b''):
        hash_value.update(chunk)
print(hash_value.hexdigest()[:12])
PYHASH
)
EXPERIMENT_REPO_COMMIT=$(git -C "$repo" rev-parse --short HEAD)
EXPERIMENT_REPO_DIRTY=0
if [[ -n $(git -C "$repo" status --porcelain --untracked-files=normal) ]]; then
    EXPERIMENT_REPO_DIRTY=1
fi
export EXPERIMENT_GEM5_SHA256 EXPERIMENT_REPO_COMMIT EXPERIMENT_REPO_DIRTY
mkdir -p "$base"
exec 8> "$base/.sweep.lock"
flock -n 8 || die "another sweep is running in $base"
state=$(mktemp -d "$base/.sweep.XXXXXX")
mkfifo "$state/timer"
exec 9<> "$state/timer"
export EXPERIMENT_BASE="$base" EXPERIMENT_STATE="$state" EXPERIMENT_VARIANT="$variant"
export EXPERIMENT_EXTRA="$extra" EXPERIMENT_GEM5="$gem5"
cleanup() {
    rm -f -- "$state"/*
    rmdir -- "$state"
}
interrupted() {
    trap '' INT TERM HUP
    echo 'Interrupted: stopping child jobs.' >&2
    touch "$state/CANCELLED"
    for file in "$state"/*.worker; do
        [[ -f "$file" ]] || continue
        read -r pid < "$file" || continue
        kill -TERM "$pid" 2>/dev/null || true
    done
    # Also kill groups directly in case a worker is blocked during cleanup.
    for file in "$state"/*.group; do
        [[ -f "$file" ]] || continue
        read -r pid < "$file" || continue
        kill -KILL -- "-$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    python3 "$repo/parse_stats.py" "$base" || true
    exit 130
}
trap interrupted INT TERM HUP
trap cleanup EXIT
for (( i=0; i<${#records[@]}; i+=5 )); do
    for core in "${core_list[@]}"; do
        printf '%s\0' "${records[@]:i:5}" "$core"
    done
done > "$state/tasks"
xargs -0 -r -n 6 -P "$jobs" "$self" --worker < "$state/tasks" &
dispatcher=$!
result=0
wait "$dispatcher" || result=$?
python3 "$repo/parse_stats.py" "$base" || result=1
done_count=0 skipped_count=0 failed_count=0
for file in "$state"/*.status; do
    [[ -f "$file" ]] || continue
    read -r status < "$file"
    run_name=${file##*/}
    run_name=${run_name%.status}
    if [[ -f "$base/$run_name/FAILED" ]]; then status=failed; fi
    case "$status" in
        done) done_count=$((done_count + 1)) ;;
        skipped) skipped_count=$((skipped_count + 1)) ;;
        failed) failed_count=$((failed_count + 1)) ;;
    esac
done
printf 'Final: %d done, %d skipped, %d failed\n' "$done_count" "$skipped_count" "$failed_count"
if [[ -s "$base/failed.txt" ]]; then
    echo 'Failed runs:'
    cat "$base/failed.txt"
    result=1
fi
exit "$result"

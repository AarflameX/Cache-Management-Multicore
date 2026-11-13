RADIOSITY is not marked fixed. No benchmark, ROI patch, pool size, threshold,
or gem5 configuration was changed in this investigation. A full naturally
completed gem5 run has not been obtained.

The strongest supported explanation of the historical defaults run's death
is external SIGTERM from its `timeout 1200` wrapper. This mechanism has been
reproduced directly. The original process's wait status/final signal trace
was not saved, so historical attribution remains an inference rather than a
recorded signal delivery for that exact PID.

The recorded launcher `/tmp/run_radiosity3.sh` contains:

```sh
timeout 1200 ./run_benchmark.sh --suite splash4 --benchmark RADIOSITY --roi --cores 2 --args "-batch -p 2 -ae 2000.0 -en 0.005" > results/q_RADIOSITY3.log 2>&1 &
```

The gem5 log says it started on 2026-11-13 at 18:02:16 IST (12:32:16 UTC),
PID 56203. Its 1,200-second deadline was 18:22:16 IST. The recorded attempted
strace attach was at 18:22:37 IST, after that deadline. This fits an automatic
timeout even though there was no manual kill or OOM. The recorded ps at
18:02:35 and attach at 18:22:37 span about 20 minutes. Other intermediate ps
observations mentioned in the question are not recorded in the available
history, so their exact times cannot be independently checked here.

In a new eight-second probe of the same defaults command, host strace recorded:

```text
63284 ... --- SIGALRM ... ---
63284 ... kill(63285, SIGTERM) = 0
63285 ... --- SIGTERM {si_code=SI_USER, si_pid=63284, ...} ---
63285 ... +++ killed by SIGTERM +++
63284 ... wait4(... WIFSIGNALED(s) && WTERMSIG(s) == SIGTERM ...)
63284 ... exit_group(124)
```

Here 63284 was timeout and 63285 was gem5. The probe returned 124 after 8.08
seconds, with zero-byte stats.txt, no Begin Simulation Statistics block, and
no gem5 panic/fatal/exit line: the same visible failure pattern. This was an
intentional diagnostic termination, not an unexpected death or a passing run.

Memory growth was observed before subdivision:

- A guest GDB snapshot of a separate supervised run stopped at PC 0x40b213,
  `init_taskq+243`, with stack `init_taskq -> init_global -> main`. Disassembly
  shows a pointer-linking loop over the preallocated task descriptors.
- MAX_TASKS is 3,276,800; sizeof(Task) is 48. The task array alone is
  157,286,400 bytes. sizeof(Global) in this build is 175,547,360 bytes.
- The guest syscall trace recorded mmap(175550464), then later mmap(384004096).
  It advanced past task initialization to element-pool allocation; this is
  finite progress, not evidence of a task initialization loop running forever.
- Default BFepsilon is 0.00015. The code multiplies element/vertex/edge pool
  capacities by 20 and interaction capacity by 30 at that threshold. Global
  plus those four pools reserve 1,679,547,360 bytes (about 1.564 GiB), before
  other storage. Changing -ae/-en does not change that early allocation policy.
- Host strace brk calls belong to the host gem5 allocator. They are not guest
  brk calls: the guest trace had only its early startup brk requests and the
  large mappings during this observation. Host growth during guest writes is
  consistent with gem5 allocating state as those large pools are touched;
  no allocation-stack profile was taken to attribute every host byte.

Relevant benchmark source paths (under src/Splash-4/radiosity):

- radiosity.h.in: default MAX_TASKS; DEFAULT_BFEPSILON.
- rad_main.c.in: initial pool counts, BFepsilon multipliers, init_global.
- taskman.c.in: init_taskq initializes a fixed number of task links. Task
  acquisition and recycling do not allocate an unbounded new heap of tasks.
- elemman.c.in: initial error_analysis returns no interaction/no refinement.
  BF refinement is limited by Area_epsilon and each subdivision quarters area;
  an already-subdivided element is not subdivided again. Object pools are
  fixed, and exhaustion prints a diagnostic and calls exit(1).
- rad_main.c.in/elemman.c.in: the outer radiosity convergence loop has no hard
  iteration cap. Non-convergence under some different numerical/queue behavior
  is possible in principle; it was not observed in the gem5 trace, which was
  still initializing before workers and the ROI.

Native two-worker runs of the same source completed with exit 0:

| Arguments | Iterations | Elements | Interactions |
| --- | ---: | ---: | ---: |
| -ae 5000 -en 0.05 | 4 | 3,070 | 926,692 |
| -ae 2000.0 -en 0.005 | 7 | 11,194 | 2,352,367 |

These are functional evidence, not proof of gem5 completion. In this checkout
DEFAULT_ENERGY_EPSILON is actually 0.00005; the second row uses the explicit
0.005 requested in the reported run, rather than silently substituting it.

The local gem5 source explains the exit cases:

- src/sim/syscall_emul.cc: unimplementedFunc emits fatal; ignore handlers warn
  and return success. exit/exit_group halt guest contexts and schedule a
  simulation exit when the last context ends.
- src/sim/syscall_emul.hh: tgkill(SIGABRT) is unusual: it calls exitGroupFunc
  with status 0. Thus a guest abort can lose its usual signal semantics, but
  this still follows guest-exit handling. No such call occurred in the traced
  run. It does not explain the observed host timeout trace.
- src/arch/x86/linux/syscall_tbl64.cc: guest rt_sigaction/rt_sigprocmask are
  ignored with warnings; kill/tkill are unimplemented in this table. They do
  not simply forward arbitrary guest signals to the host simulator process.
- src/sim/init_signals.cc: gem5 installs diagnostic handlers for SIGABRT and
  SIGSEGV and a clean-exit handler for SIGINT; it installs no SIGTERM handler
  here. The timeout trace demonstrates default host SIGTERM termination.
- src/python/m5/simulate.py registers stats.dump with atexit. Default host
  signal termination bypasses that cleanup, explaining empty stats/no exit
  line. The normal Python config prints the simulation exit cause after run.

The four-minute supervised run was deliberately stopped using host SIGINT.
It returned 0, printed `because user interrupt received`, and produced a
279,599-byte stats.txt with a Begin Simulation Statistics block. The block
reports 16,368,001 instructions and 0.223556 simulated seconds. This is an
interrupted initialization diagnostic, NOT a completed RADIOSITY run, ROI dump,
or confirmation of a fix. A statistics block alone is insufficient when the
exit cause is an intentional interrupt.

Artifacts are in results/radiosity-investigation/ (ignored build/run output):

- reproduction/{metadata.json,status.json,run.log,host.strace,guest-syscalls.log,
  guest-gdb-port7000.log,monitor.jsonl,stats.txt}
- timeout-probe/{status.json,host.strace,run.log,stats.txt}
- native-coarse.log, native-defaults.log, native-build.log, layout.txt

Next validation should run the unchanged workload without the hard SIGTERM
wrapper and retain its foreground exit status. Use a fresh output directory;
if a deliberate time limit is needed, log it explicitly and distinguish an
interrupt from normal guest completion. Do not reduce pools or alter refinement
criteria and describe that as fixing unexplained death. No such change is
proposed on the current evidence. To claim completion, require the normal
workload exit cause, successful exit status, and a nonempty statistics block;
an ROI-marked run should also reach its reset/dump calls.

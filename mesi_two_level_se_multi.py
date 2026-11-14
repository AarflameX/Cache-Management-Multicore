"""
gem5 SE-mode config: MESI_Two_Level Ruby coherence protocol.
Parameterized version — takes binary path, core count, and args on the CLI.

Usage:
  gem5.opt mesi_two_level_se_multi.py --binary <path> --cores <N> --args <benchmark's own args...>

    grep command: 
    grep -E "(simTicks|simInsts|simOps|cpi|ipc|l1_cntrl|l2_cntrl|hits|misses)" m5out/stats.txt
"""


import argparse
import shlex
from gem5.utils.requires import requires
from gem5.isas import ISA
from gem5.coherence_protocol import CoherenceProtocol
from gem5.resources.resource import BinaryResource, FileResource
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.memory import SingleChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import (
    MESITwoLevelCacheHierarchy,
)
from gem5.simulate.simulator import Simulator

requires(isa_required=ISA.X86, coherence_protocol_required=CoherenceProtocol.MESI_TWO_LEVEL)

parser = argparse.ArgumentParser()
parser.add_argument("--binary", required=True)
parser.add_argument("--cores", type=int, default=2)
parser.add_argument("--mem-size", default="4GiB", help="simulated physical memory capacity (default: 4GiB)")
parser.add_argument("--input", help="file to use as benchmark stdin")
parser.add_argument("--args", nargs=argparse.REMAINDER, default=[])
parsed = parser.parse_args()
if len(parsed.args) == 1:
    try:
        parsed.args = shlex.split(parsed.args[0])
    except ValueError as error:
        parser.error(f"invalid --args: {error}")

NUM_L2_BANKS = 2
if parsed.cores <= 0 or parsed.cores % NUM_L2_BANKS:
    parser.error(f"--cores must be a positive multiple of {NUM_L2_BANKS}")

cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1i_size="32KiB", l1i_assoc=2,
    l1d_size="32KiB", l1d_assoc=2,
    l2_size="256KiB", l2_assoc=8,
    num_l2_banks=NUM_L2_BANKS,
)
memory = SingleChannelDDR4_2400(size=parsed.mem_size)
processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=parsed.cores)
board = SimpleBoard(clk_freq="3GHz", processor=processor, memory=memory, cache_hierarchy=cache_hierarchy)

# Critical: OpenMP benchmarks read thread count from OMP_NUM_THREADS at
# runtime. gem5 SE mode does NOT inherit the host shell's environment, so
# this must be passed explicitly here, pinned to match --cores, or an
# OpenMP program will spawn more threads than there are modeled CPU
# contexts and crash on exit.
board.set_se_binary_workload(
    binary=BinaryResource(local_path=parsed.binary),
    arguments=parsed.args,
    stdin_file=FileResource(local_path=parsed.input) if parsed.input else None,
    # Park OpenMP workers promptly so exit_group does not halt a spinning CPU
    # while it has a pending memory operation in TimingSimpleCPU.
    env_list=[
        f"OMP_NUM_THREADS={parsed.cores}",
        "OMP_WAIT_POLICY=PASSIVE",
        "GOMP_SPINCOUNT=1",
    ],
)

simulator = Simulator(board=board)
simulator.run()
print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")


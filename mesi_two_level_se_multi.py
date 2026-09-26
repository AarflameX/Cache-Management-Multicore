"""
gem5 SE-mode config: MESI_Two_Level Ruby coherence protocol.
Parameterized version — takes binary path, core count, and args on the CLI.

Usage:
  gem5.opt mesi_two_level_se_multi.py --binary <path> --cores <N> --args <benchmark's own args...>

    grep command: 
    grep -E "(simTicks|simInsts|simOps|cpi|ipc|l1_cntrl|l2_cntrl|hits|misses)" m5out/stats.txt
"""


import argparse
from gem5.utils.requires import requires
from gem5.isas import ISA
from gem5.coherence_protocol import CoherenceProtocol
from gem5.resources.resource import BinaryResource
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
parser.add_argument("--args", nargs=argparse.REMAINDER, default=[])
parsed = parser.parse_args()

cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1i_size="32KiB", l1i_assoc=2,
    l1d_size="32KiB", l1d_assoc=2,
    l2_size="256KiB", l2_assoc=8,
    num_l2_banks=2,
)
memory = SingleChannelDDR4_2400(size="2GiB")
processor = SimpleProcessor(cpu_type=CPUTypes.MINOR, isa=ISA.X86, num_cores=parsed.cores)
board = SimpleBoard(clk_freq="3GHz", processor=processor, memory=memory, cache_hierarchy=cache_hierarchy)

# Critical: OpenMP benchmarks read thread count from OMP_NUM_THREADS at
# runtime. gem5 SE mode does NOT inherit the host shell's environment, so
# this must be passed explicitly here, pinned to match --cores, or an
# OpenMP program will spawn more threads than there are modeled CPU
# contexts and crash on exit.
board.set_se_binary_workload(
    binary=BinaryResource(local_path=parsed.binary),
    arguments=parsed.args,
    env_list=[f"OMP_NUM_THREADS={parsed.cores}"],
)

simulator = Simulator(board=board)
simulator.run()
print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")


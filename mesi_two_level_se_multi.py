"""
gem5 SE-mode config: MESI_Two_Level Ruby coherence protocol.
Parameterized version — takes binary path, core count, and args on the CLI.

Usage:
  gem5.opt mesi_two_level_se_multi.py --binary <path> --cores <N> --args <benchmark's own args...>

    grep command: 
    grep -E "(simTicks|simInsts|simOps|cpi|ipc|l1_cntrl|l2_cntrl|hits|misses)" m5out/stats.txt
"""


import argparse
import json
import shlex
from _m5 import core as gem5_core
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
parser.add_argument("--seed", type=int, default=5489)
parser.add_argument("--env-json", type=json.loads)
parser.add_argument("--literal-args", action="store_true")
parser.add_argument("--args", nargs=argparse.REMAINDER, default=[])
parsed = parser.parse_args()
if not parsed.literal_args and len(parsed.args) == 1:
    try:
        parsed.args = shlex.split(parsed.args[0])
    except ValueError as error:
        parser.error(f"invalid --args: {error}")

if not 0 <= parsed.seed < 2**32:
    parser.error("--seed must be an unsigned 32-bit integer")
# Keep gem5's native initialization for its built-in default.
if parsed.seed != 5489:
    gem5_core.seedRandom(parsed.seed)

NUM_L2_BANKS = 2
if parsed.cores <= 0 or parsed.cores % NUM_L2_BANKS:
    parser.error(f"--cores must be a positive multiple of {NUM_L2_BANKS}")


class BaselineMESITwoLevelCacheHierarchy(MESITwoLevelCacheHierarchy):
    def incorporate_cache(self, board):
        super().incorporate_cache(board)
        # gem5 v25.1.0.1 passes the byte count as the L1 bit position.
        line_bytes = int(board.get_cache_line_size())
        if line_bytes <= 0 or line_bytes & (line_bytes - 1):
            raise ValueError("Ruby cache line size must be a positive power of two")
        offset_bits = line_bytes.bit_length() - 1
        for controller in self.ruby_system.l1_controllers:
            controller.L1Icache.start_index_bit = offset_bits
            controller.L1Dcache.start_index_bit = offset_bits


cache_hierarchy = BaselineMESITwoLevelCacheHierarchy(
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
    env_list=parsed.env_json if parsed.env_json is not None else [
        f"OMP_NUM_THREADS={parsed.cores}",
        "OMP_WAIT_POLICY=PASSIVE",
        "GOMP_SPINCOUNT=1",
    ],
)

simulator = Simulator(board=board)
simulator.run()
print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")


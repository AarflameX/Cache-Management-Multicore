"""
gem5 standard-library config script: SE-mode simulation using the
MESI_Two_Level Ruby coherence protocol.

Works with a gem5 binary built with either:
  - scons build/X86_MESI_Two_Level/gem5.opt   (single-protocol build), or
  - scons build/ALL/gem5.opt                   (multi-protocol build, v24.1+)

Run with:
  <path/to/gem5>/build/ALL/gem5.opt mesi_two_level_se.py
    Ex: On Aarnesh's PC
    cd Gem5Workspace
    gem5-25.1.0.1/build/ALL/gem5.opt Cache-Management-Multicore/mesi_two_level_se.py
grep:
grep -E "(simTicks|simInsts|simOps|cpi|ipc|l1_cntrl|l2_cntrl|hits|misses)" m5out/stats.txt
"""

import os
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

# Enforce build dependencies (fails fast if gem5 binary lacks X86 or MESI_Two_Level)
requires(
    isa_required=ISA.X86,
    coherence_protocol_required=CoherenceProtocol.MESI_TWO_LEVEL,
)

# ==============================================================================
# 1. CACHE HIERARCHY CONFIGURATION
# ==============================================================================
# Private L1 (I + D) per core, shared banked L2.
# NOTE: num_l2_banks must be a power of 2 and divide evenly into num_cores.
cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1i_size="32KiB",
    l1i_assoc=2,
    l1d_size="32KiB",
    l1d_assoc=2,
    l2_size="256KiB",
    l2_assoc=8,
    num_l2_banks=2,
)

# ==============================================================================
# 2. MEMORY CONFIGURATION
# ==============================================================================
memory = SingleChannelDDR4_2400(size="2GiB")

# ==============================================================================
# 3. PROCESSOR CONFIGURATION
# ==============================================================================
# [CUSTOMIZABLE]: Change num_cores to match your target benchmark thread count (-p flag).
# NOTE: num_cores must be evenly divisible by num_l2_banks for MESI_Two_Level.
NUM_CORES = 2

processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING, 
    isa=ISA.X86, 
    num_cores=NUM_CORES
)

# ==============================================================================
# 4. SYSTEM BOARD
# ==============================================================================
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# ==============================================================================
# 5. WORKLOAD SETUP & BENCHMARK PATHS
# ==============================================================================
# [CUSTOMIZABLE]: Set the relative or absolute path to your target compiled benchmark binary.
# Dynamically resolves path relative to current working directory or user's workspace.
DEFAULT_BINARY_PATH = os.path.expanduser(
    "~/Gem5Workspace/Cache-Management-Multicore/benchmarks/splash-3/codes/kernels/lu/contiguous_blocks/LU"
)

# [CUSTOMIZABLE]: Benchmark arguments. 
# For SPLASH-3 LU: -p = number of threads (MUST match NUM_CORES above), -n = matrix size.
BENCHMARK_ARGS = ["-p2", "-n512"]

board.set_se_binary_workload(
    binary=BinaryResource(local_path=DEFAULT_BINARY_PATH),
    arguments=BENCHMARK_ARGS,
)

# ==============================================================================
# 6. SIMULATION RUN
# ==============================================================================
simulator = Simulator(board=board)
simulator.run()

print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")

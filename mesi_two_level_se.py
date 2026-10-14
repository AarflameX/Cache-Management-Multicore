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
  SPLASH-4 contiguous-block LU:
    gem5-25.1.0.1/build/ALL/gem5.opt Cache-Management-Multicore/mesi_two_level_se.py
      --benchmark splash4 --num-cores 2 --matrix-size 128 --block-size 16
grep:
grep -E "(simTicks|simInsts|simOps|cpi|ipc|l1_cntrl|l2_cntrl|hits|misses)" m5out/stats.txt
"""

import argparse
from pathlib import Path
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

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--benchmark", choices=("splash3", "splash4"), default="splash3",
    help="SPLASH suite supplying contiguous-block LU (default: splash3)",
)
parser.add_argument("--num-cores", type=int, default=2)
parser.add_argument("--matrix-size", type=int, default=128)
parser.add_argument("--block-size", type=int, default=16)
args = parser.parse_args()

# Keep LU's thread count and the simulated CPU contexts in sync.
NUM_CORES = args.num_cores
NUM_L2_BANKS = 2
if NUM_CORES <= 0 or NUM_CORES % NUM_L2_BANKS:
    parser.error("--num-cores must be a positive multiple of 2")
# Both suites allocate a fixed 256-entry array for pthread IDs.
if NUM_CORES > 256:
    parser.error("--num-cores cannot exceed the SPLASH thread limit of 256")
if args.matrix_size <= 0 or args.block_size <= 0:
    parser.error("--matrix-size and --block-size must be positive")

REPO_ROOT = Path(__file__).resolve().parent
BENCHMARK_PATHS = {
    "splash3": REPO_ROOT / "benchmarks/splash-3/codes/kernels/lu/contiguous_blocks/LU",
    "splash4": REPO_ROOT / "benchmarks/Splash-4/Splash-4/lu-contiguous_blocks/LU-CONT",
}
BINARY_PATH = BENCHMARK_PATHS[args.benchmark]
if not BINARY_PATH.is_file():
    build_script = (
        "build_splash4.sh lu" if args.benchmark == "splash4"
        else "build_splash3.sh"
    )
    parser.error(
        f"Binary not found: {BINARY_PATH}. "
        f"From {REPO_ROOT}, run: bash scripts/{build_script}"
    )

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
    num_l2_banks=NUM_L2_BANKS,
)

# ==============================================================================
# 2. MEMORY CONFIGURATION
# ==============================================================================
memory = SingleChannelDDR4_2400(size="2GiB")

# ==============================================================================
# 3. PROCESSOR CONFIGURATION
# ==============================================================================
# Use --num-cores to set both the core count and LU's thread count (-p flag).
# NOTE: num_cores must be evenly divisible by num_l2_banks for MESI_Two_Level.
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    isa=ISA.X86,
    num_cores=NUM_CORES,
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
# Both suites accept -p (threads), -n (matrix size), and -b (block size).
BENCHMARK_ARGS = [
    f"-p{NUM_CORES}", f"-n{args.matrix_size}", f"-b{args.block_size}",
]

board.set_se_binary_workload(
    binary=BinaryResource(local_path=str(BINARY_PATH)),
    arguments=BENCHMARK_ARGS,
)

# ==============================================================================
# 6. SIMULATION RUN
# ==============================================================================
simulator = Simulator(board=board)
simulator.run()

print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")

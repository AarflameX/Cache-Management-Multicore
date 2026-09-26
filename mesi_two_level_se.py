"""
gem5 standard-library config script: SE-mode simulation using the
MESI_Two_Level Ruby coherence protocol.

Works with a gem5 binary built with either:
  - scons build/X86_MESI_Two_Level/gem5.opt   (single-protocol build), or
  - scons build/ALL/gem5.opt                  (multi-protocol build, v24.1+)

Run with:
  build/ALL/gem5.opt mesi_two_level_se.py
"""

from gem5.utils.requires import requires
from gem5.isas import ISA
from gem5.coherence_protocol import CoherenceProtocol
from gem5.resources.resource import obtain_resource
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.memory import SingleChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import (
    MESITwoLevelCacheHierarchy,
)
from gem5.simulate.simulator import Simulator

# Fails fast with a clear error if this binary wasn't built with
# MESI_Two_Level support (instead of a cryptic crash later).
requires(
    isa_required=ISA.X86,
    coherence_protocol_required=CoherenceProtocol.MESI_TWO_LEVEL,
)

# Private L1 (I + D) per core, shared banked L2.
# num_l2_banks should divide evenly into the address space (power of 2).
cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1i_size="32KiB",
    l1i_assoc=2,
    l1d_size="32KiB",
    l1d_assoc=2,
    l2_size="256KiB",
    l2_assoc=8,
    num_l2_banks=2,
)

memory = SingleChannelDDR4_2400(size="2GiB")

# num_cores must be evenly divisible by num_l2_banks for this protocol.
processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=2)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Downloads a prebuilt x86 "Hello World" binary from gem5-resources the
# first time it's run (needs internet), then caches it locally.
board.set_se_binary_workload(obtain_resource("x86-matrix-multiply"))

simulator = Simulator(board=board)
simulator.run()

print(f"Exiting @ tick {simulator.get_current_tick()} because {simulator.get_last_exit_event_cause()}")

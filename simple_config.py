from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.memory.single_channel import SingleChannelDDR4_2400
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.simulator import Simulator

cache_hierarchy = PrivateL1SharedL2CacheHierarchy(
    l1d_size="32KiB", l1i_size="32KiB", l2_size="256KiB",
    l1d_assoc=2, l1i_assoc=2, l2_assoc=8,
)

memory = SingleChannelDDR4_2400(size="2GiB")
processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, num_cores=1, isa=ISA.X86)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

board.set_se_binary_workload(obtain_resource("x86-matrix-multiply"))

simulator = Simulator(board=board)
simulator.run()

"""PHY wrapper tests for the and_nand_test custom mode."""

from __future__ import annotations

import os
import sys

import migen
import pytest
from migen import run_simulation

pytest.importorskip("artiq")

from entangler.and_nand_test_phy import AndNandTestEntangler
from entangler.and_nand_test_registers import ADDRESS_READ
from entangler.and_nand_test_registers import ADDRESS_WRITE
from entangler.and_nand_test_registers import EDGE_MODE

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from gateware_utils import rtio_output_event  # noqa: E402
from gateware_utils import wait_until  # noqa: E402
from test_and_nand_test_core import EdgePhy  # noqa: E402


class AndNandPhyHarness(migen.Module):
    """RTIO wrapper simulation harness."""

    def __init__(self):
        self.counter = migen.Signal(11)
        self.input_states = [migen.Signal() for _ in range(2)]
        self.input_phys = [
            EdgePhy(self.counter),
            EdgePhy(self.counter),
            EdgePhy(self.counter),
            EdgePhy(self.counter),
        ]
        self.submodules += self.input_phys
        self.submodules.core = AndNandTestEntangler(
            output_pads=None,
            passthrough_sigs=None,
            input_phys=self.input_phys,
            input_states=self.input_states,
            simulate=True,
        )
        self.comb += self.counter.eq(self.core.core.m)

    def write(self, address, data):
        yield from rtio_output_event(self.core.rtlink, int(address), int(data))
        yield

    def read(self, address):
        yield from rtio_output_event(self.core.rtlink, int(address), 0)
        yield
        return (yield self.core.rtlink.i.data)


ARTIQ_CLOCKS = {"sys": 8, "rio": 8, "rio_phy": 8}


def test_phy_register_run_and_readback():
    dut = AndNandPhyHarness()

    def bench():
        yield dut.input_states[0].eq(1)
        yield dut.input_states[1].eq(1)
        yield dut.input_phys[2].edge.eq(int(EDGE_MODE.RISING))
        yield dut.input_phys[3].edge.eq(int(EDGE_MODE.RISING))
        yield dut.input_phys[2].t_event.eq(19)
        yield dut.input_phys[3].t_event.eq(37)

        config = 1 | (0b11 << 1)
        yield from dut.write(ADDRESS_WRITE.CONFIG, config)
        yield from dut.write(ADDRESS_WRITE.RUN_LENGTH, 20)
        yield from dut.write(ADDRESS_WRITE.TIMER_DIV, 2)
        yield from dut.write(ADDRESS_WRITE.CONTROL, 0b01)
        yield from wait_until(dut.core.core.done_stb, max_cycles=50)
        yield

        status = yield from dut.read(ADDRESS_READ.STATUS)
        outputs = yield from dut.read(ADDRESS_READ.OUTPUTS)
        diff0 = yield from dut.read(ADDRESS_READ.DIFF0)
        diff1 = yield from dut.read(ADDRESS_READ.DIFF1)

        assert status & (1 << 2)
        assert not (status & (1 << 3))
        assert outputs & 0b11 == 0b01
        assert diff0 == 11
        assert diff1 == 13

    run_simulation(dut, bench(), clocks=ARTIQ_CLOCKS)

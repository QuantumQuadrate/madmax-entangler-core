"""PHY wrapper tests for the atom_photon_parity custom mode."""

from __future__ import annotations

import os
import sys

import migen
import pytest
from migen import run_simulation

pytest.importorskip("artiq")

from entangler.atom_photon_parity_phy import AtomPhotonParityEntangler
from entangler.atom_photon_parity_registers import ADDRESS_READ
from entangler.atom_photon_parity_registers import ADDRESS_WRITE
from entangler.atom_photon_parity_registers import OUTCOME

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from gateware_utils import rtio_output_event  # noqa: E402
from gateware_utils import wait_until  # noqa: E402
from test_atom_photon_parity_core import PhotonPhy  # noqa: E402


class ParityPhyHarness(migen.Module):
    """RTIO wrapper simulation harness."""

    def __init__(self, *, use_input_states=False):
        self.counter = migen.Signal(11)
        self.input_phys = [PhotonPhy(self.counter) for _ in range(4)]
        self.submodules += self.input_phys
        self.input_states = [migen.Signal() for _ in range(2)]
        input_states = self.input_states if use_input_states else None
        self.submodules.core = AtomPhotonParityEntangler(
            output_pads=None,
            passthrough_sigs=None,
            input_phys=self.input_phys,
            input_states=input_states,
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
    dut = ParityPhyHarness()

    def bench():
        yield dut.input_phys[0].t_event.eq(24)

        yield from dut.write(ADDRESS_WRITE.CONFIG, 1)
        yield from dut.write(ADDRESS_WRITE.RUN_LENGTH, 80)
        yield from dut.write(ADDRESS_WRITE.NUM_ATTEMPTS, 1)
        yield from dut.write(ADDRESS_WRITE.ATTEMPT_PERIOD, 16)
        yield from dut.write(ADDRESS_WRITE.GATE, (48 << 16) | 8)
        yield from dut.write(ADDRESS_WRITE.IDLE_STATES, 0b1111)
        yield from dut.write(ADDRESS_WRITE.ACTIVE_STATES, 0b1110)
        yield from dut.write(ADDRESS_WRITE.BRANCH_DONE_DELAY, 12)
        yield from dut.write(ADDRESS_WRITE.BRANCH0_WINDOW_BASE, (8 << 16) | 5)
        yield from dut.write(ADDRESS_WRITE.CONTROL, 0b01)
        yield from wait_until(dut.core.core.done_stb, max_cycles=80)
        yield

        status = yield from dut.read(ADDRESS_READ.STATUS)
        outcome = yield from dut.read(ADDRESS_READ.OUTCOME)
        click_ts = yield from dut.read(ADDRESS_READ.CLICK_TS)

        assert status & (1 << 2)
        assert not (status & (1 << 3))
        assert outcome == int(OUTCOME.SPCM0_ONLY)
        assert click_ts == 24

    run_simulation(dut, bench(), clocks=ARTIQ_CLOCKS)


def test_phy_overlay_input_states_generate_helper_edges():
    dut = ParityPhyHarness(use_input_states=True)

    def bench():
        yield from dut.write(ADDRESS_WRITE.CONFIG, 1)
        yield from dut.write(ADDRESS_WRITE.RUN_LENGTH, 80)
        yield from dut.write(ADDRESS_WRITE.NUM_ATTEMPTS, 1)
        yield from dut.write(ADDRESS_WRITE.ATTEMPT_PERIOD, 16)
        yield from dut.write(ADDRESS_WRITE.GATE, (48 << 16) | 8)
        yield from dut.write(ADDRESS_WRITE.IDLE_STATES, 0b1111)
        yield from dut.write(ADDRESS_WRITE.ACTIVE_STATES, 0b1110)
        yield from dut.write(ADDRESS_WRITE.BRANCH_DONE_DELAY, 12)
        yield from dut.write(ADDRESS_WRITE.BRANCH0_WINDOW_BASE, (8 << 16) | 5)
        yield from dut.write(ADDRESS_WRITE.CONTROL, 0b01)

        for _ in range(3):
            yield
        yield dut.input_states[0].eq(1)
        yield
        yield dut.input_states[0].eq(0)

        yield from wait_until(dut.core.core.done_stb, max_cycles=80)
        yield

        status = yield from dut.read(ADDRESS_READ.STATUS)
        outcome = yield from dut.read(ADDRESS_READ.OUTCOME)
        click_ts = yield from dut.read(ADDRESS_READ.CLICK_TS)

        assert status & (1 << 2)
        assert not (status & (1 << 3))
        assert outcome == int(OUTCOME.SPCM0_ONLY)
        assert click_ts != 0

    run_simulation(dut, bench(), clocks=ARTIQ_CLOCKS)

"""Tests for the atom_photon_parity custom entangler core."""

from __future__ import annotations

import os
import sys

import migen
from migen import run_simulation

from entangler.atom_photon_parity_core import AtomPhotonParityCore
from entangler.atom_photon_parity_core import STATE_BRANCH
from entangler.atom_photon_parity_registers import OUTCOME

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from gateware_utils import wait_until  # noqa: E402


class PhotonPhy(migen.Module):
    """Small timestamp PHY model for SPCM edge events."""

    def __init__(self, counter):
        self.fine_ts = migen.Signal(3)
        self.stb = migen.Signal()
        self.t_event = migen.Signal(32, reset=0xFFFF)

        self.sync += [
            self.stb.eq(0),
            self.fine_ts.eq(0),
        ]
        self.comb += [
            migen.If(
                counter == self.t_event[3:],
                self.stb.eq(1),
                self.fine_ts.eq(self.t_event[:3]),
            )
        ]


class ParityHarness(migen.Module):
    """Simulation harness for the parity helper core."""

    def __init__(self):
        self.counter = migen.Signal(11)
        self.phys = [PhotonPhy(self.counter), PhotonPhy(self.counter)]
        self.submodules += self.phys
        self.submodules.core = AtomPhotonParityCore(self.phys)
        self.comb += self.counter.eq(self.core.m)


def _configure_fast_run(dut):
    yield dut.core.enable.eq(1)
    yield dut.core.run_length.eq(80)
    yield dut.core.num_attempts.eq(1)
    yield dut.core.attempt_period.eq(16)
    yield dut.core.gate_start.eq(8)
    yield dut.core.gate_stop.eq(48)
    yield dut.core.branch_done_delay.eq(12)
    yield dut.core.idle_states.eq(0b1111)
    yield dut.core.active_states.eq(0b1110)
    yield dut.core.branch0_starts[0].eq(5)
    yield dut.core.branch0_stops[0].eq(8)
    yield dut.core.branch1_starts[0].eq(5)
    yield dut.core.branch1_stops[0].eq(8)


def test_spcm0_only_schedules_click_relative_branch_output():
    dut = ParityHarness()

    def bench():
        yield from _configure_fast_run(dut)
        yield dut.phys[0].t_event.eq(24)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)

        low_seen = False
        for _ in range(40):
            outputs = yield dut.core.outputs
            state = yield dut.core.state
            if state == STATE_BRANCH and (outputs & 0b1) == 0:
                low_seen = True
            yield

        assert low_seen
        assert (yield dut.core.success) == 1
        assert (yield dut.core.timeout) == 0
        assert (yield dut.core.outcome) == int(OUTCOME.SPCM0_ONLY)
        assert (yield dut.core.click_ts) == 24
        assert (yield dut.core.done_stb) == 0

    run_simulation(dut, bench())


def test_second_attempt_click_reports_attempt_index():
    dut = ParityHarness()

    def bench():
        yield from _configure_fast_run(dut)
        yield dut.core.num_attempts.eq(2)
        yield dut.core.attempt_period.eq(8)
        yield dut.phys[1].t_event.eq(80)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)
        yield from wait_until(dut.core.done_stb, max_cycles=80)
        yield

        assert (yield dut.core.success) == 1
        assert (yield dut.core.outcome) == int(OUTCOME.SPCM1_ONLY)
        assert (yield dut.core.click_ts) == 80
        assert (yield dut.core.attempt_index) == 1

    run_simulation(dut, bench())


def test_timeout_when_no_single_detector_click_arrives():
    dut = ParityHarness()

    def bench():
        yield from _configure_fast_run(dut)
        yield dut.core.run_length.eq(30)
        yield dut.core.branch_done_delay.eq(4)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)
        yield from wait_until(dut.core.done_stb, max_cycles=60)
        yield

        assert (yield dut.core.success) == 0
        assert (yield dut.core.timeout) == 1
        assert (yield dut.core.outcome) == int(OUTCOME.NONE)

    run_simulation(dut, bench())

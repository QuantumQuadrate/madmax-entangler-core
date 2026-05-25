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


MU_PER_COARSE_CYCLE = 8


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


def test_no_click_attempt_loop_uses_configured_gateware_period():
    dut = ParityHarness()

    def bench():
        yield dut.core.enable.eq(1)
        yield dut.core.run_length.eq(200)
        yield dut.core.num_attempts.eq(4)
        yield dut.core.attempt_period.eq(16)
        yield dut.core.gate_start.eq(8)
        yield dut.core.gate_stop.eq(16)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)

        attempt_starts = []
        last_attempt_index = -1
        done_mu = None
        for _ in range(80):
            attempt_index = yield dut.core.attempt_index
            if attempt_index != last_attempt_index:
                attempt_starts.append((yield dut.core.attempt_start_m))
                last_attempt_index = attempt_index
            if (yield dut.core.done_stb):
                done_mu = (yield dut.core.m) * MU_PER_COARSE_CYCLE
                break
            yield

        assert attempt_starts == [0, 16, 32, 48]
        assert done_mu == 416
        assert (yield dut.core.success) == 0
        assert (yield dut.core.timeout) == 1
        assert (yield dut.core.outcome) == int(OUTCOME.NONE)

    run_simulation(dut, bench())


def test_branch_output_timing_is_click_coarse_relative():
    branch_output = 2
    branch_mask = 1 << branch_output
    branch_start = 16
    branch_stop = 20

    for fine_phase in range(MU_PER_COARSE_CYCLE):
        dut = ParityHarness()
        click_mu = 24 + fine_phase
        edges = []

        def bench():
            yield dut.core.enable.eq(1)
            yield dut.core.run_length.eq(80)
            yield dut.core.num_attempts.eq(1)
            yield dut.core.attempt_period.eq(32)
            yield dut.core.gate_start.eq(8)
            yield dut.core.gate_stop.eq(48)
            yield dut.core.branch_done_delay.eq(branch_stop + 1)
            yield dut.core.idle_states.eq(0)
            yield dut.core.active_states.eq(branch_mask)
            yield dut.core.branch0_starts[branch_output].eq(branch_start)
            yield dut.core.branch0_stops[branch_output].eq(branch_stop)
            yield dut.phys[0].t_event.eq(click_mu)

            yield dut.core.start_stb.eq(1)
            yield
            yield dut.core.start_stb.eq(0)

            last_active = 0
            for _ in range(80):
                active = 1 if (yield dut.core.outputs) & branch_mask else 0
                if active != last_active:
                    edges.append(((yield dut.core.m) * MU_PER_COARSE_CYCLE, active))
                    last_active = active
                if (yield dut.core.done_stb):
                    break
                yield

            assert (yield dut.core.success) == 1
            assert (yield dut.core.timeout) == 0
            assert (yield dut.core.outcome) == int(OUTCOME.SPCM0_ONLY)
            assert (yield dut.core.click_ts) == click_mu

        run_simulation(dut, bench())

        expected_rise_mu = ((click_mu >> 3) + branch_start) * MU_PER_COARSE_CYCLE
        expected_fall_mu = ((click_mu >> 3) + branch_stop) * MU_PER_COARSE_CYCLE
        exact_rise_mu = click_mu + branch_start * MU_PER_COARSE_CYCLE

        assert edges == [(expected_rise_mu, 1), (expected_fall_mu, 0)]
        assert expected_rise_mu - exact_rise_mu == -fine_phase

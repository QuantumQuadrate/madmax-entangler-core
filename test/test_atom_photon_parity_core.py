"""Test the atom-photon parity gateware prototype."""

import os
import sys

from migen import run_simulation

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from atom_photon_tester import (  # noqa: E402 pylint: disable=import-error
    NO_EVENT_MU,
    AtomPhotonParityHarness,
    collect_until_done,
)

from entangler.atom_photon_registers import ActionOutput, BranchPolicy, DoneReason, PhotonOutcome


CLOCKS = {"sys": 8}


def test_spcm0_only_branch(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path()
        yield from dut.set_clicks(spcm0_mu=32, spcm1_mu=NO_EVENT_MU)
        yield from dut.start()
        samples = yield from collect_until_done(dut)
        assert (yield dut.core.success) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.SPCM0_ONLY)
        assert (yield dut.core.chosen_timestamp_mu) == 32
        assert (yield dut.core.attempts_completed) == 1
        assert samples == [
            (112, 1 << int(ActionOutput.MW_SWITCH), 1 << int(ActionOutput.MW_SWITCH)),
            (120, 1 << int(ActionOutput.MW_SWITCH), 1 << int(ActionOutput.MW_SWITCH)),
        ]

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_spcm1_only_branch(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path()
        yield from dut.set_clicks(spcm0_mu=NO_EVENT_MU, spcm1_mu=40)
        yield from dut.start()
        samples = yield from collect_until_done(dut)
        assert (yield dut.core.success) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.SPCM1_ONLY)
        assert (yield dut.core.chosen_timestamp_mu) == 40
        assert samples == [
            (120, 1 << int(ActionOutput.RF_SWITCH), 1 << int(ActionOutput.RF_SWITCH)),
            (128, 1 << int(ActionOutput.RF_SWITCH), 1 << int(ActionOutput.RF_SWITCH)),
        ]

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_both_click_case(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path(both_policy=BranchPolicy.STOP_FAIL)
        yield from dut.set_clicks(spcm0_mu=32, spcm1_mu=48)
        yield from dut.start()
        yield from collect_until_done(dut)
        assert (yield dut.core.success) == 0
        assert (yield dut.core.failed) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.BOTH)
        assert (yield dut.core.done_reason) == int(DoneReason.BOTH)

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_neither_click_case(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path(neither_policy=BranchPolicy.STOP_FAIL)
        yield from dut.set_clicks()
        yield from dut.start()
        yield from collect_until_done(dut)
        assert (yield dut.core.success) == 0
        assert (yield dut.core.failed) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.NEITHER)
        assert (yield dut.core.done_reason) == int(DoneReason.NEITHER)

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_retry_across_multiple_attempts(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path(
            n_attempts=3,
            neither_policy=BranchPolicy.RETRY,
        )
        yield from dut.set_clicks(spcm0_mu=160, spcm1_mu=NO_EVENT_MU)
        yield from dut.start()
        yield from collect_until_done(dut, max_cycles=260)
        assert (yield dut.core.success) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.SPCM0_ONLY)
        assert (yield dut.core.chosen_timestamp_mu) == 160
        assert (yield dut.core.attempts_completed) == 2

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_done_after_action_playback(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path(action_offset_mu=96, action_duration_mu=24)
        yield from dut.set_clicks(spcm0_mu=32, spcm1_mu=NO_EVENT_MU)
        yield from dut.start()
        samples = yield from collect_until_done(dut)
        assert samples[-1][0] == 144
        assert (yield dut.core.done_stb) == 1
        yield
        assert (yield dut.core.running) == 0

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)


def test_invalid_window_reaches_invalid_config(request):
    dut = AtomPhotonParityHarness()

    def bench():
        yield from dut.configure_critical_path(gate_start_mu=64, gate_stop_mu=16)
        assert (yield dut.core.invalid_config) == 1
        yield from dut.start()
        yield from collect_until_done(dut, max_cycles=20)
        assert (yield dut.core.failed) == 1
        assert (yield dut.core.final_outcome) == int(PhotonOutcome.INVALID)
        assert (yield dut.core.done_reason) == int(DoneReason.INVALID_CONFIG)

    run_simulation(dut, bench(), vcd_name=request.node.name + ".vcd", clocks=CLOCKS)

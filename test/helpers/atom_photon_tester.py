"""Simulation harness for the atom-photon parity core."""

import os
import sys

import migen

sys.path.append(os.path.dirname(__file__))

from gateware_utils import MockPhy  # noqa: E402 pylint: disable=import-error

from entangler.atom_photon_core import AtomPhotonParityCore
from entangler.atom_photon_registers import (
    COARSE_COUNTER_WIDTH,
    ActionOutput,
    BranchPolicy,
)


NO_EVENT_MU = (1 << 28) * 8


class AtomPhotonParityHarness(migen.Module):
    """Wrap the parity core with two mock SPCM PHYs."""

    def __init__(self):
        self.counter = migen.Signal(COARSE_COUNTER_WIDTH)
        self.submodules.spcm0 = MockPhy(self.counter)
        self.submodules.spcm1 = MockPhy(self.counter)
        self.submodules.core = AtomPhotonParityCore(
            [self.spcm0, self.spcm1], coarse_counter=self.counter
        )

    def configure_critical_path(
        self,
        *,
        n_attempts=1,
        attempt_period_mu=128,
        gate_start_mu=16,
        gate_stop_mu=64,
        action_offset_mu=80,
        action_duration_mu=16,
        branch0_output=ActionOutput.MW_SWITCH,
        branch1_output=ActionOutput.RF_SWITCH,
        neither_policy=BranchPolicy.STOP_FAIL,
        both_policy=BranchPolicy.STOP_FAIL,
    ):
        core = self.core
        yield core.n_attempts.eq(n_attempts)
        yield core.attempt_period_mu.eq(attempt_period_mu)
        yield core.fort_off_mu.eq(0)
        yield core.fort_on_mu.eq(72)
        yield core.excitation_start_mu.eq(8)
        yield core.excitation_stop_mu.eq(24)
        yield core.photon_gate_start_mu.eq(gate_start_mu)
        yield core.photon_gate_stop_mu.eq(gate_stop_mu)
        yield core.neither_policy.eq(int(neither_policy))
        yield core.both_policy.eq(int(both_policy))

        yield core.actions.action_count[0].eq(1)
        yield core.actions.action_offsets_mu[0][0].eq(action_offset_mu)
        yield core.actions.action_durations_mu[0][0].eq(action_duration_mu)
        yield core.actions.action_masks[0][0].eq(1 << int(branch0_output))
        yield core.actions.action_values[0][0].eq(1 << int(branch0_output))

        yield core.actions.action_count[1].eq(1)
        yield core.actions.action_offsets_mu[1][0].eq(action_offset_mu)
        yield core.actions.action_durations_mu[1][0].eq(action_duration_mu)
        yield core.actions.action_masks[1][0].eq(1 << int(branch1_output))
        yield core.actions.action_values[1][0].eq(1 << int(branch1_output))

    def set_clicks(self, spcm0_mu=NO_EVENT_MU, spcm1_mu=NO_EVENT_MU):
        yield self.spcm0.t_event.eq(spcm0_mu)
        yield self.spcm1.t_event.eq(spcm1_mu)

    def start(self):
        yield self.core.start_stb.eq(1)
        yield
        yield self.core.start_stb.eq(0)


def collect_until_done(dut: AtomPhotonParityHarness, max_cycles=200):
    """Run until done and collect action output samples by machine-unit time."""

    samples = []
    done_seen = False
    for _ in range(max_cycles):
        now_mu = (yield dut.core.coarse_counter) << 3
        enable = yield dut.core.action_output_enable
        value = yield dut.core.action_output_value
        if enable:
            samples.append((now_mu, enable, value))
        if (yield dut.core.done_stb):
            done_seen = True
            break
        yield
    assert done_seen
    return samples

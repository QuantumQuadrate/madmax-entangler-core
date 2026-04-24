"""Test host-side atom-photon parity configuration helpers."""

import pytest

from entangler.atom_photon_driver import (
    MIN_BRANCH_ACTION_OFFSET_MU,
    AtomPhotonParityConfig,
    BranchAction,
    microwave_mapping_actions,
)
from entangler.atom_photon_registers import (
    MAX_BRANCH_ACTIONS,
    ActionOutput,
    AtomPhotonWrite,
    BranchPolicy,
    action_entry_registers,
)


def _valid_config(**overrides):
    values = dict(
        n_excitation_attempts=3,
        attempt_period_mu=128,
        fort_off_mu=0,
        fort_on_mu=72,
        excitation_start_mu=8,
        excitation_stop_mu=24,
        photon_gate_start_mu=16,
        photon_gate_stop_mu=64,
        branch0_actions=(
            BranchAction.pulse(ActionOutput.MW_SWITCH, 80, 16),
        ),
        branch1_actions=(
            BranchAction.pulse(ActionOutput.RF_SWITCH, 80, 16),
        ),
        neither_policy=BranchPolicy.RETRY,
        both_policy=BranchPolicy.STOP_FAIL,
    )
    values.update(overrides)
    return AtomPhotonParityConfig(**values)


def test_host_configuration_register_writes():
    config = _valid_config()
    writes = dict(config.iter_register_writes())
    assert writes[int(AtomPhotonWrite.N_ATTEMPTS)] == 3
    assert writes[int(AtomPhotonWrite.ATTEMPT_PERIOD_MU)] == 128
    assert writes[int(AtomPhotonWrite.FORT_OFF_MU)] == 0
    assert writes[int(AtomPhotonWrite.FORT_ON_MU)] == 72
    assert writes[int(AtomPhotonWrite.EXCITATION_START_MU)] == 8
    assert writes[int(AtomPhotonWrite.EXCITATION_STOP_MU)] == 24
    assert writes[int(AtomPhotonWrite.PHOTON_GATE_START_MU)] == 16
    assert writes[int(AtomPhotonWrite.PHOTON_GATE_STOP_MU)] == 64
    assert writes[int(AtomPhotonWrite.BRANCH0_ACTION_COUNT)] == 1
    assert writes[int(AtomPhotonWrite.BRANCH1_ACTION_COUNT)] == 1
    assert writes[int(AtomPhotonWrite.BRANCH_POLICIES)] == (
        int(BranchPolicy.RETRY) | (int(BranchPolicy.STOP_FAIL) << 4)
    )

    offset_addr, duration_addr, mask_addr, value_addr = action_entry_registers(0, 0)
    assert writes[offset_addr] == 80
    assert writes[duration_addr] == 16
    assert writes[mask_addr] == 1 << int(ActionOutput.MW_SWITCH)
    assert writes[value_addr] == 1 << int(ActionOutput.MW_SWITCH)


def test_microwave_mapping_action_builder():
    actions = microwave_mapping_actions(
        80,
        16,
        rf_start_offset_mu=112,
        rf_duration_mu=24,
        blow_away_offset_mu=160,
        blow_away_duration_mu=8,
        parity_readout_offset_mu=184,
        parity_readout_duration_mu=32,
    )
    assert [action.output_value for action in actions] == [
        1 << int(ActionOutput.MW_SWITCH),
        1 << int(ActionOutput.RF_SWITCH),
        1 << int(ActionOutput.BLOW_AWAY),
        1 << int(ActionOutput.PARITY_READOUT),
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"n_excitation_attempts": 0},
        {"photon_gate_start_mu": 0},
        {"photon_gate_stop_mu": 16, "photon_gate_start_mu": 16},
        {"attempt_period_mu": 64},
        {"excitation_stop_mu": 8},
        {"fort_on_mu": 0},
    ],
)
def test_invalid_timing_rejected(overrides):
    with pytest.raises(ValueError):
        _valid_config(**overrides).validate()


def test_invalid_action_offset_rejected():
    min_safe_offset = 64 - 16 + MIN_BRANCH_ACTION_OFFSET_MU
    with pytest.raises(ValueError):
        _valid_config(
            branch0_actions=(
                BranchAction.pulse(
                    ActionOutput.MW_SWITCH,
                    min_safe_offset - 1,
                    16,
                ),
            )
        ).validate()


def test_too_many_actions_rejected():
    actions = tuple(
        BranchAction.pulse(ActionOutput.MW_SWITCH, 80 + 8 * i, 8)
        for i in range(MAX_BRANCH_ACTIONS + 1)
    )
    with pytest.raises(ValueError):
        _valid_config(branch0_actions=actions).validate()

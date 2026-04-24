"""Register and result constants for the atom-photon parity sequencer."""

from __future__ import annotations

import enum


TIMING_WIDTH = 32
FINE_TS_BITS = 3
COARSE_COUNTER_WIDTH = TIMING_WIDTH - FINE_TS_BITS
MAX_BRANCH_ACTIONS = 8
NUM_ACTION_BRANCHES = 2
ACTION_WORDS_PER_ENTRY = 4
ACTION_TABLE_BASE = 0x30
ACTION_BRANCH_STRIDE = MAX_BRANCH_ACTIONS * ACTION_WORDS_PER_ENTRY


class PhotonOutcome(enum.IntEnum):
    """Explicit photon branch outcomes."""

    NEITHER = 0
    SPCM0_ONLY = 1
    SPCM1_ONLY = 2
    BOTH = 3
    INVALID = 4


class BranchPolicy(enum.IntEnum):
    """Policy for non-exclusive photon outcomes."""

    RETRY = 0
    STOP_FAIL = 1


class DoneReason(enum.IntEnum):
    """Terminal reason codes reported by the sequencer."""

    IDLE = 0
    SUCCESS = 1
    NEITHER = 2
    BOTH = 3
    MAX_ATTEMPTS = 4
    INVALID_CONFIG = 5
    CLEARED = 6


class ActionOutput(enum.IntEnum):
    """Suggested output-bit mapping for the branch action table."""

    FORT_GATE = 0
    EXCITATION_GATE = 1
    MW_SWITCH = 2
    RF_SWITCH = 3
    DDS_PROFILE_TRIGGER = 4
    BLOW_AWAY = 5
    PARITY_READOUT = 6
    ATOM_CHECK_OR_RECOOLING = 7


class AtomPhotonWrite(enum.IntEnum):
    """Top-level write registers for the future RTIO PHY wrapper."""

    CONFIG = 0x00
    CONTROL = 0x01
    N_ATTEMPTS = 0x02
    ATTEMPT_PERIOD_MU = 0x03
    FORT_OFF_MU = 0x04
    FORT_ON_MU = 0x05
    EXCITATION_START_MU = 0x06
    EXCITATION_STOP_MU = 0x07
    PHOTON_GATE_START_MU = 0x08
    PHOTON_GATE_STOP_MU = 0x09
    BRANCH_POLICIES = 0x0A
    ATOM_CHECK_CONTROL = 0x0B
    ATOM_CHECK_GATE_START_MU = 0x0C
    ATOM_CHECK_GATE_STOP_MU = 0x0D
    ATOM_CHECK_THRESHOLD = 0x0E
    RECOOLING_START_MU = 0x0F
    RECOOLING_STOP_MU = 0x10
    BRANCH0_ACTION_COUNT = 0x11
    BRANCH1_ACTION_COUNT = 0x12


class AtomPhotonRead(enum.IntEnum):
    """Top-level read registers for the future RTIO PHY wrapper."""

    STATUS = 0x80
    OUTCOME = 0x81
    DONE_REASON = 0x82
    ATTEMPTS_COMPLETED = 0x83
    SPCM0_TIMESTAMP_MU = 0x84
    SPCM1_TIMESTAMP_MU = 0x85
    CHOSEN_TIMESTAMP_MU = 0x86
    ATOM_CHECK_COUNTS = 0x87


def action_entry_base(branch: int, index: int) -> int:
    """Return the base register for an action-table entry."""

    if branch < 0 or branch >= NUM_ACTION_BRANCHES:
        raise ValueError("branch must be 0 or 1")
    if index < 0 or index >= MAX_BRANCH_ACTIONS:
        raise ValueError("action index outside table")
    return ACTION_TABLE_BASE + branch * ACTION_BRANCH_STRIDE + index * ACTION_WORDS_PER_ENTRY


def action_entry_registers(branch: int, index: int) -> tuple[int, int, int, int]:
    """Return offset, duration, mask, and value registers for one action."""

    base = action_entry_base(branch, index)
    return base, base + 1, base + 2, base + 3

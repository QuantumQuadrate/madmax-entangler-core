"""Register constants for the atom_photon_parity entangler mode."""

from __future__ import annotations

import enum


class ADDRESS_WRITE(enum.IntEnum):
    """RTIO output addresses accepted by :mod:`atom_photon_parity_phy`."""

    CONFIG = 0x00
    CONTROL = 0x01
    RUN_LENGTH = 0x02
    NUM_ATTEMPTS = 0x03
    ATTEMPT_PERIOD = 0x04
    GATE = 0x05
    IDLE_STATES = 0x06
    ACTIVE_STATES = 0x07
    BRANCH_DONE_DELAY = 0x08

    ATTEMPT_WINDOW_BASE = 0x10
    BRANCH0_WINDOW_BASE = 0x20
    BRANCH1_WINDOW_BASE = 0x30


class ADDRESS_READ(enum.IntEnum):
    """RTIO input/readback addresses returned by :mod:`atom_photon_parity_phy`."""

    STATUS = 0x80
    OUTCOME = 0x81
    CLICK_TS = 0x82
    SPCM0_TS = 0x83
    SPCM1_TS = 0x84
    ATTEMPT_INDEX = 0x85
    OUTPUTS = 0x86


class OUTCOME(enum.IntEnum):
    """Photon classification result for the terminal attempt."""

    NONE = 0
    SPCM0_ONLY = 1
    SPCM1_ONLY = 2
    BOTH = 3


STATUS_READY = 1 << 0
STATUS_RUNNING = 1 << 1
STATUS_SUCCESS = 1 << 2
STATUS_TIMEOUT = 1 << 3
STATUS_INVALID_CONFIG = 1 << 4
STATUS_CAPTURED_SHIFT = 8
STATUS_OUTCOME_SHIFT = 16

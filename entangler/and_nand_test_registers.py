"""Register constants for the and_nand_test entangler mode."""

from __future__ import annotations

import enum


class ADDRESS_WRITE(enum.IntEnum):
    """RTIO output addresses accepted by :mod:`and_nand_test_phy`."""

    CONFIG = 0x00
    CONTROL = 0x01
    RUN_LENGTH = 0x02
    TIMER_DIV = 0x03


class ADDRESS_READ(enum.IntEnum):
    """RTIO input/readback addresses returned by :mod:`and_nand_test_phy`."""

    STATUS = 0x80
    OUTPUTS = 0x81
    TIMER0_TS = 0x82
    TIMER1_TS = 0x83
    INPUT0_TS = 0x84
    INPUT1_TS = 0x85
    DIFF0 = 0x86
    DIFF1 = 0x87


class EDGE_MODE(enum.IntEnum):
    """Timestamp edge selection for capture channels."""

    RISING = 0
    FALLING = 1
    BOTH = 2


STATUS_READY = 1 << 0
STATUS_RUNNING = 1 << 1
STATUS_SUCCESS = 1 << 2
STATUS_TIMEOUT = 1 << 3
STATUS_INVALID_CONFIG = 1 << 4
STATUS_CAPTURED_SHIFT = 8
STATUS_TIMER_VALUE_SHIFT = 16

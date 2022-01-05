"""Enums describing the Entangler PHY registers, given current Entangler settings."""
import enum
import math

import numpy

from entangler.config import settings


# generate the PHY read/write addresses, b/c ARTIQ kernel had issues w/ referencing dynaconf settings
def max_value_to_bit_width(max_value: int) -> int:
    """Calculate how many bits are needed to represent an unsigned int."""
    return math.ceil(math.log2(max_value))


_num_channels = settings.NUM_ENTANGLER_INPUT_SIGNALS + settings.NUM_OUTPUT_CHANNELS
_channel_bits = max_value_to_bit_width(_num_channels)
_read_start = 0b1 << (_channel_bits + 1)
assert _channel_bits <= 30


class ADDRESS_WRITE(enum.IntEnum):
    """PHY Addresses to configure the Entangler."""

    CONFIG = 0
    RUN = 1
    TCYCLE = 2
    PATTERNS = 3
    TIMING = 0b1 << _channel_bits


class ADDRESS_READ(enum.IntEnum):
    """PHY Addresses to get information from the Entangler."""

    STATUS = _read_start + 0
    NCYCLES = _read_start + 1
    TIME_REMAINING = _read_start + 2
    NTRIGGERS = _read_start + 3
    TIMESTAMP = numpy.int32(0b11 << _channel_bits)

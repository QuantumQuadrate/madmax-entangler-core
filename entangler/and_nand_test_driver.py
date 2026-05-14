"""ARTIQ kernel driver for the and_nand_test custom entangler mode."""

from __future__ import annotations

import numpy as np
from artiq.coredevice.rtio import rtio_input_data
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.coredevice.rtio import rtio_output
from artiq.language.core import delay_mu
from artiq.language.core import kernel
from artiq.language.types import TInt32
from artiq.language.types import TTuple
from artiq.language.types import TInt64

from entangler.and_nand_test_registers import ADDRESS_READ
from entangler.and_nand_test_registers import ADDRESS_WRITE
from entangler.and_nand_test_registers import EDGE_MODE


class AndNandTestEntangler:
    """Driver for the AND/NAND timer timestamp test core."""

    kernel_invariants = {
        "core",
        "channel",
        "ref_period_mu",
        "_ADDRESS_READ",
        "_ADDRESS_WRITE",
    }

    def __init__(self, dmgr, channel, core_device="core"):
        self.core = dmgr.get(core_device)
        self.channel = channel
        self.ref_period_mu = self.core.seconds_to_mu(self.core.coarse_ref_period)
        self._ADDRESS_READ = ADDRESS_READ
        self._ADDRESS_WRITE = ADDRESS_WRITE

    @kernel
    def _write(self, addr: TInt32, value: TInt32):
        rtio_output((self.channel << 8) | addr, value)
        delay_mu(self.ref_period_mu)

    @kernel
    def _read(self, addr: TInt32) -> TInt32:
        rtio_output((self.channel << 8) | addr, 0)
        return rtio_input_data(self.channel)

    @kernel
    def init(self):
        self.clear()
        self.configure(True, 0b11, EDGE_MODE.RISING, EDGE_MODE.RISING)

    @kernel
    def configure(
        self,
        enable: bool = True,
        capture_enable: TInt32 = 0b11,
        edge0: TInt32 = EDGE_MODE.RISING,
        edge1: TInt32 = EDGE_MODE.RISING,
    ):
        data = 0
        if enable:
            data |= 1
        data |= (capture_enable & 0b11) << 1
        data |= (edge0 & 0b11) << 4
        data |= (edge1 & 0b11) << 6
        self._write(self._ADDRESS_WRITE.CONFIG, data)

    @kernel
    def clear(self):
        self._write(self._ADDRESS_WRITE.CONTROL, 0b10)

    @kernel
    def set_run_length_mu(self, run_length_mu: TInt32):
        self._write(self._ADDRESS_WRITE.RUN_LENGTH, run_length_mu >> 3)

    @kernel
    def set_timer_div(self, timer_div_coarse: TInt32):
        self._write(self._ADDRESS_WRITE.TIMER_DIV, timer_div_coarse)

    @kernel
    def start(self) -> TTuple([TInt64, TInt32]):
        self._write(self._ADDRESS_WRITE.CONTROL, 0b01)
        return rtio_input_timestamped_data(np.int64(-1), self.channel)

    @kernel
    def get_status(self) -> TInt32:
        return self._read(self._ADDRESS_READ.STATUS)

    @kernel
    def get_outputs(self) -> TInt32:
        return self._read(self._ADDRESS_READ.OUTPUTS)

    @kernel
    def get_timer_timestamp_mu(self, index: TInt32) -> TInt32:
        if index == 0:
            return self._read(self._ADDRESS_READ.TIMER0_TS)
        return self._read(self._ADDRESS_READ.TIMER1_TS)

    @kernel
    def get_input_timestamp_mu(self, index: TInt32) -> TInt32:
        if index == 0:
            return self._read(self._ADDRESS_READ.INPUT0_TS)
        return self._read(self._ADDRESS_READ.INPUT1_TS)

    @kernel
    def get_difference_mu(self, index: TInt32) -> TInt32:
        if index == 0:
            return self._read(self._ADDRESS_READ.DIFF0)
        return self._read(self._ADDRESS_READ.DIFF1)


Entangler = AndNandTestEntangler

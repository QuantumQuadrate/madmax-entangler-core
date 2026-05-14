"""ARTIQ kernel driver for the atom_photon_parity custom entangler mode."""

from __future__ import annotations

import numpy as np
from artiq.coredevice.rtio import rtio_input_data
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.coredevice.rtio import rtio_output
from artiq.language.core import delay_mu
from artiq.language.core import kernel
from artiq.language.types import TInt32
from artiq.language.types import TInt64
from artiq.language.types import TTuple

from entangler.atom_photon_parity_registers import ADDRESS_READ
from entangler.atom_photon_parity_registers import ADDRESS_WRITE


class AtomPhotonParityEntangler:
    """Driver for the atom-photon parity gateware helper."""

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
        self.configure(True)

    @kernel
    def configure(self, enable: bool = True):
        data = 1 if enable else 0
        self._write(self._ADDRESS_WRITE.CONFIG, data)

    @kernel
    def clear(self):
        self._write(self._ADDRESS_WRITE.CONTROL, 0b10)

    @kernel
    def set_run_length_mu(self, run_length_mu: TInt32):
        self._write(self._ADDRESS_WRITE.RUN_LENGTH, run_length_mu >> 3)

    @kernel
    def set_num_attempts(self, attempts: TInt32):
        self._write(self._ADDRESS_WRITE.NUM_ATTEMPTS, attempts)

    @kernel
    def set_attempt_period_mu(self, period_mu: TInt32):
        self._write(self._ADDRESS_WRITE.ATTEMPT_PERIOD, period_mu >> 3)

    @kernel
    def set_gate_mu(self, start_mu: TInt32, stop_mu: TInt32):
        self._write(self._ADDRESS_WRITE.GATE, ((stop_mu & 0xFFFF) << 16) | (start_mu & 0xFFFF))

    @kernel
    def set_output_states(self, idle_states: TInt32, active_states: TInt32):
        self._write(self._ADDRESS_WRITE.IDLE_STATES, idle_states)
        self._write(self._ADDRESS_WRITE.ACTIVE_STATES, active_states)

    @kernel
    def set_branch_done_delay_mu(self, delay_mu_value: TInt32):
        self._write(self._ADDRESS_WRITE.BRANCH_DONE_DELAY, delay_mu_value >> 3)

    @kernel
    def set_attempt_window_mu(self, output: TInt32, start_mu: TInt32, stop_mu: TInt32):
        self._write(
            self._ADDRESS_WRITE.ATTEMPT_WINDOW_BASE + output,
            (((stop_mu >> 3) & 0xFFFF) << 16) | ((start_mu >> 3) & 0xFFFF),
        )

    @kernel
    def set_branch_window_mu(
        self,
        branch: TInt32,
        output: TInt32,
        start_mu: TInt32,
        stop_mu: TInt32,
    ):
        base = self._ADDRESS_WRITE.BRANCH0_WINDOW_BASE
        if branch == 1:
            base = self._ADDRESS_WRITE.BRANCH1_WINDOW_BASE
        self._write(
            base + output,
            (((stop_mu >> 3) & 0xFFFF) << 16) | ((start_mu >> 3) & 0xFFFF),
        )

    @kernel
    def start(self) -> TTuple([TInt64, TInt32]):
        self._write(self._ADDRESS_WRITE.CONTROL, 0b01)
        return rtio_input_timestamped_data(np.int64(-1), self.channel)

    @kernel
    def get_status(self) -> TInt32:
        return self._read(self._ADDRESS_READ.STATUS)

    @kernel
    def get_outcome(self) -> TInt32:
        return self._read(self._ADDRESS_READ.OUTCOME)

    @kernel
    def get_click_timestamp_mu(self) -> TInt32:
        return self._read(self._ADDRESS_READ.CLICK_TS)

    @kernel
    def get_spcm_timestamp_mu(self, index: TInt32) -> TInt32:
        if index == 0:
            return self._read(self._ADDRESS_READ.SPCM0_TS)
        return self._read(self._ADDRESS_READ.SPCM1_TS)

    @kernel
    def get_attempt_index(self) -> TInt32:
        return self._read(self._ADDRESS_READ.ATTEMPT_INDEX)


Entangler = AtomPhotonParityEntangler

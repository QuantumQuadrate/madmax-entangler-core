"""Gateware core for the atom_photon_parity custom entangler mode.

The core targets the timing-critical section of
``atom_photon_parity_6_experiment``: collect one photon window from SPCM0/SPCM1,
classify exactly-one-detector events, and schedule output pulses relative to the
captured photon timestamp.
"""

from __future__ import annotations

import typing

from migen import Cat
from migen import Constant
from migen import If
from migen import Module
from migen import Mux
from migen import Signal

from entangler.atom_photon_parity_registers import OUTCOME
from entangler.config import settings


STATE_IDLE = 0
STATE_ATTEMPT = 1
STATE_BRANCH = 2


class AtomPhotonParityCore(Module):
    """SPCM gate, single-click classifier, and branch action sequencer."""

    NUM_SPCM_INPUTS = 2

    def __init__(self, spcm_phys: typing.Sequence[typing.Any]):
        assert len(spcm_phys) >= self.NUM_SPCM_INPUTS

        num_outputs = settings.NUM_OUTPUT_CHANNELS

        self.enable = Signal()
        self.start_stb = Signal()
        self.clear = Signal()

        self.run_length = Signal(settings.COARSE_COUNTER_WIDTH, reset=2047)
        self.num_attempts = Signal(8, reset=1)
        self.attempt_period = Signal(settings.COARSE_COUNTER_WIDTH, reset=256)
        self.gate_start = Signal(settings.FULL_COUNTER_WIDTH, reset=8)
        self.gate_stop = Signal(settings.FULL_COUNTER_WIDTH, reset=208)
        self.branch_done_delay = Signal(settings.COARSE_COUNTER_WIDTH, reset=2047)

        self.idle_states = Signal(num_outputs, reset=(1 << num_outputs) - 1)
        self.active_states = Signal(num_outputs)

        self.attempt_starts = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]
        self.attempt_stops = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]
        self.branch0_starts = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]
        self.branch0_stops = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]
        self.branch1_starts = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]
        self.branch1_stops = [
            Signal(settings.COARSE_COUNTER_WIDTH) for _ in range(num_outputs)
        ]

        self.m = Signal(settings.COARSE_COUNTER_WIDTH)
        self.state = Signal(2, reset=STATE_IDLE)
        self.running = Signal()
        self.done_stb = Signal()
        self.success = Signal()
        self.timeout = Signal()
        self.invalid_config = Signal()
        self.ready = Signal()

        self.outputs = Signal(num_outputs)
        self.outcome = Signal(2, reset=int(OUTCOME.NONE))
        self.attempt_index = Signal(8)
        self.attempt_start_m = Signal(settings.COARSE_COUNTER_WIDTH)
        self.click_ts = Signal(settings.FULL_COUNTER_WIDTH)
        self.input_timestamps = [
            Signal(settings.FULL_COUNTER_WIDTH) for _ in range(self.NUM_SPCM_INPUTS)
        ]
        self.captured = Signal(self.NUM_SPCM_INPUTS)

        # # #

        self.comb += [
            self.ready.eq(~self.running),
            self.invalid_config.eq(
                (self.num_attempts == 0)
                | (self.attempt_period == 0)
                | (self.run_length == 0)
                | (self.gate_start >= self.gate_stop)
                | (self.gate_stop[3:] >= self.attempt_period)
            ),
        ]

        attempt_elapsed = Signal(settings.COARSE_COUNTER_WIDTH)
        branch_elapsed = Signal(settings.COARSE_COUNTER_WIDTH)
        click_coarse = Signal(settings.COARSE_COUNTER_WIDTH)
        self.comb += [
            attempt_elapsed.eq(self.m - self.attempt_start_m),
            click_coarse.eq(self.click_ts[3:]),
            branch_elapsed.eq(self.m - click_coarse),
        ]

        attempt_start_full = Signal(settings.FULL_COUNTER_WIDTH)
        now_full = Signal(settings.FULL_COUNTER_WIDTH)
        gate_abs_start = Signal(settings.FULL_COUNTER_WIDTH)
        gate_abs_stop = Signal(settings.FULL_COUNTER_WIDTH)
        self.comb += [
            attempt_start_full.eq(Cat(Constant(0, 3), self.attempt_start_m)),
            now_full.eq(Cat(Constant(0, 3), self.m)),
            gate_abs_start.eq(attempt_start_full + self.gate_start),
            gate_abs_stop.eq(attempt_start_full + self.gate_stop),
        ]

        input_ts = [
            Signal(settings.FULL_COUNTER_WIDTH) for _ in range(self.NUM_SPCM_INPUTS)
        ]
        input_in_gate = [Signal() for _ in range(self.NUM_SPCM_INPUTS)]
        for index, phy in enumerate(spcm_phys[: self.NUM_SPCM_INPUTS]):
            self.comb += [
                input_ts[index].eq(Cat(phy.fine_ts, self.m)),
                input_in_gate[index].eq(
                    (input_ts[index] >= gate_abs_start)
                    & (input_ts[index] <= gate_abs_stop)
                ),
            ]

        spcm0_only = Signal()
        spcm1_only = Signal()
        gate_done = Signal()
        attempt_period_done = Signal()
        final_attempt = Signal()
        run_timeout = Signal()
        branch_done = Signal()
        self.comb += [
            spcm0_only.eq(self.captured[0] & ~self.captured[1]),
            spcm1_only.eq(~self.captured[0] & self.captured[1]),
            gate_done.eq(now_full > gate_abs_stop),
            attempt_period_done.eq(attempt_elapsed >= self.attempt_period),
            final_attempt.eq((self.attempt_index + 1) >= self.num_attempts),
            run_timeout.eq(self.m >= self.run_length),
            branch_done.eq(branch_elapsed >= self.branch_done_delay),
        ]

        for index in range(num_outputs):
            attempt_active = Signal()
            branch_start = Signal(settings.COARSE_COUNTER_WIDTH)
            branch_stop = Signal(settings.COARSE_COUNTER_WIDTH)
            branch_active = Signal()
            window_active = Signal()

            self.comb += [
                attempt_active.eq(
                    (self.state == STATE_ATTEMPT)
                    & (attempt_elapsed >= self.attempt_starts[index])
                    & (attempt_elapsed < self.attempt_stops[index])
                ),
                branch_start.eq(
                    Mux(
                        self.outcome == int(OUTCOME.SPCM0_ONLY),
                        self.branch0_starts[index],
                        self.branch1_starts[index],
                    )
                ),
                branch_stop.eq(
                    Mux(
                        self.outcome == int(OUTCOME.SPCM0_ONLY),
                        self.branch0_stops[index],
                        self.branch1_stops[index],
                    )
                ),
                branch_active.eq(
                    (self.state == STATE_BRANCH)
                    & (branch_elapsed >= branch_start)
                    & (branch_elapsed < branch_stop)
                ),
                window_active.eq(attempt_active | branch_active),
                self.outputs[index].eq(
                    Mux(window_active, self.active_states[index], self.idle_states[index])
                ),
            ]

        clear_run_state = [
            self.running.eq(0),
            self.state.eq(STATE_IDLE),
            self.done_stb.eq(0),
            self.success.eq(0),
            self.timeout.eq(0),
            self.m.eq(0),
            self.attempt_index.eq(0),
            self.attempt_start_m.eq(0),
            self.outcome.eq(int(OUTCOME.NONE)),
            self.click_ts.eq(0),
            self.captured.eq(0),
            *[ts.eq(0) for ts in self.input_timestamps],
        ]

        start_new_attempt = [
            self.attempt_index.eq(self.attempt_index + 1),
            self.attempt_start_m.eq(self.attempt_start_m + self.attempt_period),
            self.captured.eq(0),
            self.outcome.eq(int(OUTCOME.NONE)),
            self.click_ts.eq(0),
            *[ts.eq(0) for ts in self.input_timestamps],
        ]

        self.sync += [
            self.done_stb.eq(0),
            If(
                self.clear,
                *clear_run_state,
            ).Elif(
                self.start_stb,
                self.m.eq(0),
                self.attempt_index.eq(0),
                self.attempt_start_m.eq(0),
                self.outcome.eq(int(OUTCOME.NONE)),
                self.click_ts.eq(0),
                self.captured.eq(0),
                self.success.eq(0),
                self.timeout.eq(0),
                *[ts.eq(0) for ts in self.input_timestamps],
                If(
                    self.enable & ~self.invalid_config,
                    self.running.eq(1),
                    self.state.eq(STATE_ATTEMPT),
                ).Else(
                    self.running.eq(0),
                    self.state.eq(STATE_IDLE),
                    self.timeout.eq(1),
                    self.done_stb.eq(1),
                ),
            ).Elif(
                self.running,
                self.m.eq(self.m + 1),
                *[
                    If(
                        getattr(spcm_phys[index], "stb")
                        & ~self.captured[index]
                        & input_in_gate[index]
                        & (self.state == STATE_ATTEMPT),
                        self.input_timestamps[index].eq(input_ts[index]),
                        self.captured[index].eq(1),
                    )
                    for index in range(self.NUM_SPCM_INPUTS)
                ],
                If(
                    run_timeout,
                    self.running.eq(0),
                    self.state.eq(STATE_IDLE),
                    self.timeout.eq(1),
                    self.done_stb.eq(1),
                ).Elif(
                    self.state == STATE_ATTEMPT,
                    If(
                        gate_done,
                        If(
                            spcm0_only,
                            self.success.eq(1),
                            self.outcome.eq(int(OUTCOME.SPCM0_ONLY)),
                            self.click_ts.eq(self.input_timestamps[0]),
                            self.state.eq(STATE_BRANCH),
                        ).Elif(
                            spcm1_only,
                            self.success.eq(1),
                            self.outcome.eq(int(OUTCOME.SPCM1_ONLY)),
                            self.click_ts.eq(self.input_timestamps[1]),
                            self.state.eq(STATE_BRANCH),
                        ).Elif(
                            final_attempt,
                            self.running.eq(0),
                            self.state.eq(STATE_IDLE),
                            self.timeout.eq(1),
                            self.done_stb.eq(1),
                            If(
                                self.captured == 0b11,
                                self.outcome.eq(int(OUTCOME.BOTH)),
                            ).Else(
                                self.outcome.eq(int(OUTCOME.NONE)),
                            ),
                        ).Elif(
                            attempt_period_done,
                            *start_new_attempt,
                        ),
                    ),
                ).Elif(
                    self.state == STATE_BRANCH,
                    If(
                        branch_done,
                        self.running.eq(0),
                        self.state.eq(STATE_IDLE),
                        self.done_stb.eq(1),
                    ),
                ),
            ),
        ]

"""Gateware core for the and_nand_test custom entangler mode.

The mode uses four DIO inputs and four DIO outputs:

* input 0 and input 1 are sampled as logic levels.
* output 0 is ``input0 AND input1``.
* output 1 is ``NAND(input0, input1)``.
* output 2 and output 3 are the low two bits of a coarse hardware timer.
* input 2 and input 3 timestamp looped-back timer edges and report the
  difference between the captured input edge and the corresponding timer edge.
"""

from __future__ import annotations

import typing

from migen import Cat
from migen import Constant
from migen import If
from migen import Module
from migen import Signal

from entangler.and_nand_test_registers import EDGE_MODE
from entangler.config import settings


class AndNandTestCore(Module):
    """Custom AND/NAND plus two-bit timer timestamp core."""

    NUM_LOGIC_INPUTS = 2
    NUM_TIMESTAMP_INPUTS = 2
    NUM_OUTPUTS = 4

    def __init__(
        self,
        logic_input_levels: typing.Sequence[Signal],
        timestamp_phys: typing.Sequence[typing.Any],
    ):
        assert len(logic_input_levels) == self.NUM_LOGIC_INPUTS
        assert len(timestamp_phys) == self.NUM_TIMESTAMP_INPUTS

        self.enable = Signal()
        self.start_stb = Signal()
        self.clear = Signal()

        self.run_length = Signal(settings.COARSE_COUNTER_WIDTH, reset=64)
        self.timer_div = Signal(settings.COARSE_COUNTER_WIDTH, reset=1)
        self.capture_enable = Signal(self.NUM_TIMESTAMP_INPUTS, reset=0b11)
        self.edge_modes = [
            Signal(2, reset=int(EDGE_MODE.RISING))
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]

        self.m = Signal(settings.COARSE_COUNTER_WIDTH)
        self.running = Signal()
        self.done_stb = Signal()
        self.success = Signal()
        self.timeout = Signal()
        self.invalid_config = Signal()
        self.ready = Signal()

        self.timer_value = Signal(2)
        self.outputs = Signal(self.NUM_OUTPUTS)

        self.timer_timestamps = [
            Signal(settings.FULL_COUNTER_WIDTH)
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]
        self.input_timestamps = [
            Signal(settings.FULL_COUNTER_WIDTH)
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]
        self.diffs = [
            Signal((settings.FULL_COUNTER_WIDTH + 1, True))
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]
        self.captured = Signal(self.NUM_TIMESTAMP_INPUTS)

        # # #

        and_value = Signal()
        self.comb += [
            and_value.eq(logic_input_levels[0] & logic_input_levels[1]),
            self.outputs[0].eq(and_value),
            self.outputs[1].eq(~and_value),
            self.outputs[2].eq(self.timer_value[0]),
            self.outputs[3].eq(self.timer_value[1]),
            self.ready.eq(~self.running),
            self.invalid_config.eq(
                (self.run_length == 0)
                | (self.timer_div == 0)
                | (self.capture_enable == 0)
            ),
        ]

        enabled_captures = Signal(self.NUM_TIMESTAMP_INPUTS)
        success_now = Signal()
        self.comb += [
            enabled_captures.eq(self.captured & self.capture_enable),
            success_now.eq(enabled_captures == self.capture_enable),
        ]

        timer_div_counter = Signal(settings.COARSE_COUNTER_WIDTH)
        timer_tick = Signal()
        next_timer_value = Signal(2)
        self.comb += [
            timer_tick.eq(timer_div_counter == (self.timer_div - 1)),
            next_timer_value.eq(self.timer_value + 1),
        ]

        timer_timestamp = Signal(settings.FULL_COUNTER_WIDTH)
        self.comb += timer_timestamp.eq(Cat(Constant(0, 3), self.m))

        input_timestamps = [
            Signal(settings.FULL_COUNTER_WIDTH)
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]
        edge_matches = [
            Signal()
            for _ in range(self.NUM_TIMESTAMP_INPUTS)
        ]
        for index, phy in enumerate(timestamp_phys):
            fine_ts = getattr(phy, "fine_ts")
            input_edge = getattr(phy, "edge", None)
            if input_edge is None:
                input_edge = Signal(reset=int(EDGE_MODE.RISING))
            self.comb += [
                input_timestamps[index].eq(Cat(fine_ts, self.m)),
                edge_matches[index].eq(
                    (self.edge_modes[index] == int(EDGE_MODE.BOTH))
                    | (self.edge_modes[index] == input_edge)
                ),
            ]

        finish_success = Signal()
        finish_timeout = Signal()
        self.comb += [
            finish_success.eq(self.running & success_now),
            finish_timeout.eq(self.running & (self.m >= self.run_length)),
        ]

        self.sync += [
            self.done_stb.eq(0),
            If(
                self.clear,
                self.running.eq(0),
                self.done_stb.eq(0),
                self.success.eq(0),
                self.timeout.eq(0),
                self.m.eq(0),
                self.timer_value.eq(0),
                timer_div_counter.eq(0),
                self.captured.eq(0),
                *[ts.eq(0) for ts in self.timer_timestamps],
                *[ts.eq(0) for ts in self.input_timestamps],
                *[diff.eq(0) for diff in self.diffs],
            ).Elif(
                self.start_stb,
                self.success.eq(0),
                self.timeout.eq(0),
                self.m.eq(0),
                self.timer_value.eq(0),
                timer_div_counter.eq(0),
                self.captured.eq(0),
                *[ts.eq(0) for ts in self.timer_timestamps],
                *[ts.eq(0) for ts in self.input_timestamps],
                *[diff.eq(0) for diff in self.diffs],
                If(
                    self.enable & ~self.invalid_config,
                    self.running.eq(1),
                ).Else(
                    self.running.eq(0),
                    self.timeout.eq(1),
                    self.done_stb.eq(1),
                ),
            ).Elif(
                self.running,
                self.m.eq(self.m + 1),
                If(
                    timer_tick,
                    timer_div_counter.eq(0),
                    self.timer_value.eq(next_timer_value),
                    If(
                        (self.timer_value[0] != next_timer_value[0])
                        & ~self.captured[0],
                        self.timer_timestamps[0].eq(timer_timestamp),
                    ),
                    If(
                        (self.timer_value[1] != next_timer_value[1])
                        & ~self.captured[1],
                        self.timer_timestamps[1].eq(timer_timestamp),
                    ),
                ).Else(
                    timer_div_counter.eq(timer_div_counter + 1),
                ),
                *[
                    If(
                        getattr(timestamp_phys[index], "stb")
                        & self.capture_enable[index]
                        & ~self.captured[index]
                        & edge_matches[index],
                        self.input_timestamps[index].eq(input_timestamps[index]),
                        self.diffs[index].eq(
                            input_timestamps[index] - self.timer_timestamps[index]
                        ),
                        self.captured[index].eq(1),
                    )
                    for index in range(self.NUM_TIMESTAMP_INPUTS)
                ],
                If(
                    finish_success,
                    self.running.eq(0),
                    self.success.eq(1),
                    self.done_stb.eq(1),
                ).Elif(
                    finish_timeout,
                    self.running.eq(0),
                    self.timeout.eq(1),
                    self.done_stb.eq(1),
                ),
            ),
        ]

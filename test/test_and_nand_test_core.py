"""Tests for the and_nand_test custom entangler core."""

from __future__ import annotations

import os
import sys

import migen
from migen import run_simulation

from entangler.and_nand_test_core import AndNandTestCore
from entangler.and_nand_test_registers import EDGE_MODE

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from gateware_utils import wait_until  # noqa: E402


class EdgePhy(migen.Module):
    """Small timestamp PHY model with explicit edge polarity."""

    def __init__(self, counter):
        self.fine_ts = migen.Signal(3)
        self.stb = migen.Signal()
        self.edge = migen.Signal(2, reset=int(EDGE_MODE.RISING))
        self.t_event = migen.Signal(32, reset=0xFFFF)

        self.sync += [
            self.stb.eq(0),
            self.fine_ts.eq(0),
        ]
        self.comb += [
            migen.If(
                counter == self.t_event[3:],
                self.stb.eq(1),
                self.fine_ts.eq(self.t_event[:3]),
            )
        ]


def _make_dut():
    counter = migen.Signal(11)
    logic_inputs = [migen.Signal() for _ in range(2)]
    phys = [EdgePhy(counter) for _ in range(2)]

    class Harness(migen.Module):
        def __init__(self):
            self.logic_inputs = logic_inputs
            self.timestamp_phys = phys
            self.submodules += phys
            self.submodules.core = AndNandTestCore(logic_inputs, phys)
            self.comb += counter.eq(self.core.m)

    return Harness()


def test_and_nand_outputs_follow_logic_inputs():
    dut = _make_dut()

    def bench():
        combinations = [
            (0, 0, 0, 1),
            (1, 0, 0, 1),
            (0, 1, 0, 1),
            (1, 1, 1, 0),
        ]
        for a, b, and_expected, nand_expected in combinations:
            yield dut.logic_inputs[0].eq(a)
            yield dut.logic_inputs[1].eq(b)
            yield
            outputs = yield dut.core.outputs
            assert outputs & 0b01 == and_expected
            assert (outputs >> 1) & 0b01 == nand_expected

    run_simulation(dut, bench())


def test_timer_loopback_timestamp_differences():
    dut = _make_dut()

    def bench():
        yield dut.core.enable.eq(1)
        yield dut.core.run_length.eq(20)
        yield dut.core.timer_div.eq(2)
        yield dut.core.capture_enable.eq(0b11)
        yield dut.timestamp_phys[0].edge.eq(int(EDGE_MODE.RISING))
        yield dut.timestamp_phys[1].edge.eq(int(EDGE_MODE.RISING))
        yield dut.timestamp_phys[0].t_event.eq(19)
        yield dut.timestamp_phys[1].t_event.eq(37)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)
        yield from wait_until(dut.core.done_stb, max_cycles=40)
        yield

        assert (yield dut.core.success) == 1
        assert (yield dut.core.timeout) == 0
        assert (yield dut.core.timer_timestamps[0]) == 8
        assert (yield dut.core.timer_timestamps[1]) == 24
        assert (yield dut.core.input_timestamps[0]) == 19
        assert (yield dut.core.input_timestamps[1]) == 37
        assert (yield dut.core.diffs[0]) == 11
        assert (yield dut.core.diffs[1]) == 13

    run_simulation(dut, bench())


def test_timeout_when_loopback_edges_do_not_arrive():
    dut = _make_dut()

    def bench():
        yield dut.core.enable.eq(1)
        yield dut.core.run_length.eq(8)
        yield dut.core.timer_div.eq(2)
        yield dut.core.capture_enable.eq(0b11)
        yield dut.timestamp_phys[0].t_event.eq(0xFFFF)
        yield dut.timestamp_phys[1].t_event.eq(0xFFFF)

        yield dut.core.start_stb.eq(1)
        yield
        yield dut.core.start_stb.eq(0)
        yield from wait_until(dut.core.done_stb, max_cycles=20)
        yield

        assert (yield dut.core.success) == 0
        assert (yield dut.core.timeout) == 1
        assert (yield dut.core.captured) == 0

    run_simulation(dut, bench())

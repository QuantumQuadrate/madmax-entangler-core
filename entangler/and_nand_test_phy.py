"""ARTIQ RTIO PHY wrapper for the and_nand_test custom mode."""

from __future__ import annotations

import logging
import typing

from artiq.gateware.rtio import rtlink
from migen import Case
from migen import ClockDomainsRenamer
from migen import If
from migen import Instance
from migen import Module
from migen import Mux
from migen import Signal

from entangler.and_nand_test_core import AndNandTestCore
from entangler.and_nand_test_registers import ADDRESS_READ
from entangler.and_nand_test_registers import ADDRESS_WRITE
from entangler.and_nand_test_registers import STATUS_CAPTURED_SHIFT
from entangler.and_nand_test_registers import STATUS_TIMER_VALUE_SHIFT

_LOGGER = logging.getLogger(__name__)


class AndNandTestEntangler(Module):
    """RTIO-facing wrapper for :class:`AndNandTestCore`."""

    def __init__(
        self,
        output_pads,
        passthrough_sigs: typing.Sequence[Signal],
        input_phys: typing.Sequence[typing.Any],
        input_states: typing.Sequence[Signal] | None = None,
        output_overrides: typing.Sequence[typing.Sequence[Signal]] | None = None,
        simulate: bool = False,
    ):
        assert len(input_phys) >= 4

        if input_states is None:
            input_states = [
                getattr(phy, "input_state", None)
                for phy in input_phys[:2]
            ]
        if any(state is None for state in input_states):
            _LOGGER.warning(
                "and_nand_test instantiated without TTL input_state signals; "
                "logic inputs will stay low"
            )
            input_states = [Signal(reset=0), Signal(reset=0)]

        if not simulate and output_overrides is None:
            assert output_pads is not None and len(output_pads) >= 4
            assert passthrough_sigs is not None and len(passthrough_sigs) >= 4

        self.rtlink = rtlink.Interface(
            rtlink.OInterface(data_width=32, address_width=8, enable_replace=False),
            rtlink.IInterface(data_width=32, timestamped=True),
        )

        self.submodules.core = ClockDomainsRenamer("rio")(
            AndNandTestCore(input_states[:2], input_phys[2:4])
        )

        if output_overrides is not None:
            if len(output_overrides) < 4:
                raise ValueError("Not enough output overrides for and_nand_test")
            for index, overrides in enumerate(output_overrides[:4]):
                override_en, override_o = overrides[:2]
                self.comb += [
                    override_en.eq(self.core.enable),
                    override_o.eq(self.core.outputs[index]),
                ]
        elif not simulate:
            for index, pad in enumerate(output_pads[:4]):
                self.specials += Instance(
                    "OBUFDS",
                    i_I=Mux(
                        self.core.enable,
                        self.core.outputs[index],
                        passthrough_sigs[index],
                    ),
                    o_O=pad.p,
                    o_OB=pad.n,
                )

        status = Signal(32)
        self.comb += [
            status[0].eq(self.core.ready),
            status[1].eq(self.core.running),
            status[2].eq(self.core.success),
            status[3].eq(self.core.timeout),
            status[4].eq(self.core.invalid_config),
            status[
                STATUS_CAPTURED_SHIFT : STATUS_CAPTURED_SHIFT
                + len(self.core.captured)
            ].eq(self.core.captured),
            status[
                STATUS_TIMER_VALUE_SHIFT : STATUS_TIMER_VALUE_SHIFT
                + len(self.core.timer_value)
            ].eq(self.core.timer_value),
        ]

        outputs = Signal(32)
        self.comb += outputs.eq(self.core.outputs)

        read_data = Signal(32)
        self.comb += Case(
            self.rtlink.o.address,
            {
                ADDRESS_READ.STATUS: read_data.eq(status),
                ADDRESS_READ.OUTPUTS: read_data.eq(outputs),
                ADDRESS_READ.TIMER0_TS: read_data.eq(self.core.timer_timestamps[0]),
                ADDRESS_READ.TIMER1_TS: read_data.eq(self.core.timer_timestamps[1]),
                ADDRESS_READ.INPUT0_TS: read_data.eq(self.core.input_timestamps[0]),
                ADDRESS_READ.INPUT1_TS: read_data.eq(self.core.input_timestamps[1]),
                ADDRESS_READ.DIFF0: read_data.eq(self.core.diffs[0]),
                ADDRESS_READ.DIFF1: read_data.eq(self.core.diffs[1]),
            },
        )

        read_stb = Signal()
        self.sync.rio += [
            self.core.start_stb.eq(0),
            self.core.clear.eq(0),
            read_stb.eq(0),
            If(
                self.rtlink.o.stb,
                If(
                    self.rtlink.o.address == ADDRESS_WRITE.CONFIG,
                    self.core.enable.eq(self.rtlink.o.data[0]),
                    self.core.capture_enable.eq(self.rtlink.o.data[1:3]),
                    self.core.edge_modes[0].eq(self.rtlink.o.data[4:6]),
                    self.core.edge_modes[1].eq(self.rtlink.o.data[6:8]),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.CONTROL,
                    self.core.start_stb.eq(self.rtlink.o.data[0]),
                    self.core.clear.eq(self.rtlink.o.data[1]),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.RUN_LENGTH,
                    self.core.run_length.eq(self.rtlink.o.data[:len(self.core.run_length)]),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.TIMER_DIV,
                    self.core.timer_div.eq(self.rtlink.o.data[:len(self.core.timer_div)]),
                ).Elif(
                    self.rtlink.o.address[7],
                    read_stb.eq(1),
                ),
            ),
        ]

        self.comb += [
            self.rtlink.o.busy.eq(0),
            self.rtlink.i.stb.eq(read_stb | self.core.done_stb),
            self.rtlink.i.data.eq(Mux(self.core.done_stb, status, read_data)),
        ]


Entangler = AndNandTestEntangler

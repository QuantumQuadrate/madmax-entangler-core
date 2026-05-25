"""ARTIQ RTIO PHY wrapper for the atom_photon_parity custom mode."""

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

from entangler.atom_photon_parity_core import AtomPhotonParityCore
from entangler.atom_photon_parity_registers import ADDRESS_READ
from entangler.atom_photon_parity_registers import ADDRESS_WRITE
from entangler.atom_photon_parity_registers import STATUS_CAPTURED_SHIFT
from entangler.atom_photon_parity_registers import STATUS_OUTCOME_SHIFT

_LOGGER = logging.getLogger(__name__)


class _InputStateEdgePhy(Module):
    """Minimal rising-edge timestamp source for overlay DIO input states."""

    def __init__(self, input_state):
        self.fine_ts = Signal(3)
        self.stb = Signal()

        input_state_d = Signal()
        self.sync.rio += [
            input_state_d.eq(input_state),
            self.stb.eq(input_state & ~input_state_d),
            self.fine_ts.eq(0),
        ]


class AtomPhotonParityEntangler(Module):
    """RTIO-facing wrapper for :class:`AtomPhotonParityCore`."""

    def __init__(
        self,
        output_pads,
        passthrough_sigs: typing.Sequence[Signal],
        input_phys: typing.Sequence[typing.Any],
        input_states: typing.Sequence[Signal] | None = None,
        output_overrides: typing.Sequence[typing.Sequence[Signal]] | None = None,
        simulate: bool = False,
    ):
        assert len(input_phys) >= 2

        if not simulate and output_overrides is None:
            assert output_pads is not None
            assert passthrough_sigs is not None

        self.rtlink = rtlink.Interface(
            rtlink.OInterface(data_width=32, address_width=8, enable_replace=False),
            rtlink.IInterface(data_width=32, timestamped=True),
        )

        spcm_phys = input_phys[:2]
        if input_states is not None:
            if len(input_states) < 2:
                raise ValueError("Not enough input states for atom_photon_parity")
            if any(state is None for state in input_states[:2]):
                _LOGGER.warning(
                    "atom_photon_parity instantiated without DIO input_state "
                    "signals; falling back to RTIO input event strobes"
                )
            else:
                spcm_phys = [_InputStateEdgePhy(state) for state in input_states[:2]]
                self.submodules += spcm_phys

        self.submodules.core = ClockDomainsRenamer("rio")(
            AtomPhotonParityCore(spcm_phys)
        )

        if output_overrides is not None:
            if len(output_overrides) < len(self.core.outputs):
                raise ValueError("Not enough output overrides for atom_photon_parity")
            for index, overrides in enumerate(output_overrides[: len(self.core.outputs)]):
                override_en, override_o = overrides[:2]
                self.comb += [
                    override_en.eq(self.core.enable),
                    override_o.eq(self.core.outputs[index]),
                ]
        elif not simulate:
            if len(output_pads) < len(self.core.outputs):
                raise ValueError("Not enough output pads for atom_photon_parity")
            if len(passthrough_sigs) < len(self.core.outputs):
                raise ValueError("Not enough passthrough signals for atom_photon_parity")
            for index, pad in enumerate(output_pads[: len(self.core.outputs)]):
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
            status[STATUS_OUTCOME_SHIFT : STATUS_OUTCOME_SHIFT + 2].eq(
                self.core.outcome
            ),
        ]

        read_data = Signal(32)
        self.comb += Case(
            self.rtlink.o.address,
            {
                ADDRESS_READ.STATUS: read_data.eq(status),
                ADDRESS_READ.OUTCOME: read_data.eq(self.core.outcome),
                ADDRESS_READ.CLICK_TS: read_data.eq(self.core.click_ts),
                ADDRESS_READ.SPCM0_TS: read_data.eq(self.core.input_timestamps[0]),
                ADDRESS_READ.SPCM1_TS: read_data.eq(self.core.input_timestamps[1]),
                ADDRESS_READ.ATTEMPT_INDEX: read_data.eq(self.core.attempt_index),
                ADDRESS_READ.OUTPUTS: read_data.eq(self.core.outputs),
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
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.CONTROL,
                    self.core.start_stb.eq(self.rtlink.o.data[0]),
                    self.core.clear.eq(self.rtlink.o.data[1]),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.RUN_LENGTH,
                    self.core.run_length.eq(
                        self.rtlink.o.data[: len(self.core.run_length)]
                    ),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.NUM_ATTEMPTS,
                    self.core.num_attempts.eq(
                        self.rtlink.o.data[: len(self.core.num_attempts)]
                    ),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.ATTEMPT_PERIOD,
                    self.core.attempt_period.eq(
                        self.rtlink.o.data[: len(self.core.attempt_period)]
                    ),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.GATE,
                    self.core.gate_start.eq(self.rtlink.o.data[:16]),
                    self.core.gate_stop.eq(self.rtlink.o.data[16:]),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.IDLE_STATES,
                    self.core.idle_states.eq(
                        self.rtlink.o.data[: len(self.core.idle_states)]
                    ),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.ACTIVE_STATES,
                    self.core.active_states.eq(
                        self.rtlink.o.data[: len(self.core.active_states)]
                    ),
                ).Elif(
                    self.rtlink.o.address == ADDRESS_WRITE.BRANCH_DONE_DELAY,
                    self.core.branch_done_delay.eq(
                        self.rtlink.o.data[: len(self.core.branch_done_delay)]
                    ),
                ).Elif(
                    self.rtlink.o.address[7],
                    read_stb.eq(1),
                ),
            ),
        ]

        for index in range(len(self.core.outputs)):
            self.sync.rio += If(
                self.rtlink.o.stb,
                If(
                    self.rtlink.o.address
                    == int(ADDRESS_WRITE.ATTEMPT_WINDOW_BASE) + index,
                    self.core.attempt_starts[index].eq(self.rtlink.o.data[:16]),
                    self.core.attempt_stops[index].eq(self.rtlink.o.data[16:]),
                ).Elif(
                    self.rtlink.o.address
                    == int(ADDRESS_WRITE.BRANCH0_WINDOW_BASE) + index,
                    self.core.branch0_starts[index].eq(self.rtlink.o.data[:16]),
                    self.core.branch0_stops[index].eq(self.rtlink.o.data[16:]),
                ).Elif(
                    self.rtlink.o.address
                    == int(ADDRESS_WRITE.BRANCH1_WINDOW_BASE) + index,
                    self.core.branch1_starts[index].eq(self.rtlink.o.data[:16]),
                    self.core.branch1_stops[index].eq(self.rtlink.o.data[16:]),
                ),
            )

        self.comb += [
            self.rtlink.o.busy.eq(0),
            self.rtlink.i.stb.eq(read_stb | self.core.done_stb),
            self.rtlink.i.data.eq(Mux(self.core.done_stb, status, read_data)),
        ]


Entangler = AtomPhotonParityEntangler

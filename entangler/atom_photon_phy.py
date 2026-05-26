"""RTIO PHY wrapper for the atom-photon parity gateware path."""

import logging
import typing

from artiq.gateware.rtio import rtlink
from migen import Case
from migen import Cat
from migen import ClockDomainsRenamer
from migen import If
from migen import Instance
from migen import Module
from migen import Mux
from migen import Signal
from migen.fhdl.structure import Constant as Const

from entangler.atom_photon_core import AtomPhotonParityCore
from entangler.atom_photon_registers import (
    MAX_BRANCH_ACTIONS,
    TIMING_WIDTH,
    ActionOutput,
    AtomPhotonRead,
    AtomPhotonWrite,
    action_entry_registers,
)
from entangler.config import settings

_LOGGER = logging.getLogger(__name__)


class AtomPhotonParity(Module):
    """ARTIQ RTIO-facing atom-photon parity entangler.

    Physical output mapping is fixed for the experiment-specific path:

    - output 0: FORT gate/off control
    - output 1: excitation/GRIN gate
    - output 2: microwave switch action
    - output 3: RF/MW-RF switch action
    - output 4: DDS/profile trigger action
    - output 5: blow-away trigger action
    - output 6: parity readout trigger action
    - output 7: atom-check or recooling trigger action
    """

    def __init__(
        self,
        core_link_pads,
        output_pads,
        passthrough_sigs: typing.Sequence[Signal],
        input_phys: typing.Sequence["PHY"],
        reference_phy=None,
        input_states=None,
        output_overrides=None,
        simulate: bool = False,
    ):
        if reference_phy is not None:
            raise ValueError("atom-photon parity mode does not use reference_phy")
        if core_link_pads not in (None, []):
            raise ValueError("atom-photon parity mode does not use inter-Kasli links")

        num_inputs = settings.NUM_ENTANGLER_INPUT_SIGNALS
        num_outputs = settings.NUM_OUTPUT_CHANNELS
        if num_inputs < 2:
            raise ValueError("atom-photon parity mode requires at least two SPCM inputs")
        if num_outputs < 4:
            raise ValueError("atom-photon parity mode expects at least four outputs")

        self.enable = Signal()
        self.output_signals = Signal(num_outputs)

        self.rtlink = rtlink.Interface(
            rtlink.OInterface(data_width=32, address_width=8, enable_replace=False),
            rtlink.IInterface(data_width=32, timestamped=True),
        )

        assert len(input_phys) >= 2
        if not simulate:
            if output_overrides is None:
                assert len(output_pads) in (num_outputs, num_outputs + 1)
                assert len(passthrough_sigs) == num_outputs
            else:
                assert output_pads in (None, [])
                assert len(output_overrides) == num_outputs

        self.submodules.core = ClockDomainsRenamer("rio")(
            AtomPhotonParityCore(input_phys, num_action_outputs=num_outputs)
        )

        self.comb += self.rtlink.o.busy.eq(0)

        self.comb += [
            self.core.start_stb.eq(
                self.rtlink.o.stb
                & (self.rtlink.o.address == int(AtomPhotonWrite.CONTROL))
                & self.rtlink.o.data[0]
            ),
            self.core.clear.eq(
                self.rtlink.o.stb
                & (self.rtlink.o.address == int(AtomPhotonWrite.CONTROL))
                & self.rtlink.o.data[1]
            ),
        ]

        write_cases = {
            int(AtomPhotonWrite.CONFIG): [self.enable.eq(self.rtlink.o.data[0])],
            int(AtomPhotonWrite.N_ATTEMPTS): [
                self.core.n_attempts.eq(self.rtlink.o.data[:16])
            ],
            int(AtomPhotonWrite.ATTEMPT_PERIOD_MU): [
                self.core.attempt_period_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.FORT_OFF_MU): [
                self.core.fort_off_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.FORT_ON_MU): [
                self.core.fort_on_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.EXCITATION_START_MU): [
                self.core.excitation_start_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.EXCITATION_STOP_MU): [
                self.core.excitation_stop_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.PHOTON_GATE_START_MU): [
                self.core.photon_gate_start_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.PHOTON_GATE_STOP_MU): [
                self.core.photon_gate_stop_mu.eq(self.rtlink.o.data)
            ],
            int(AtomPhotonWrite.BRANCH_POLICIES): [
                self.core.neither_policy.eq(self.rtlink.o.data[0]),
                self.core.both_policy.eq(self.rtlink.o.data[4]),
            ],
            int(AtomPhotonWrite.BRANCH0_ACTION_COUNT): [
                self.core.actions.action_count[0].eq(self.rtlink.o.data[:4])
            ],
            int(AtomPhotonWrite.BRANCH1_ACTION_COUNT): [
                self.core.actions.action_count[1].eq(self.rtlink.o.data[:4])
            ],
        }

        for branch in range(2):
            for index in range(MAX_BRANCH_ACTIONS):
                offset_addr, duration_addr, mask_addr, value_addr = (
                    action_entry_registers(branch, index)
                )
                write_cases[offset_addr] = [
                    self.core.actions.action_offsets_mu[branch][index].eq(
                        self.rtlink.o.data
                    )
                ]
                write_cases[duration_addr] = [
                    self.core.actions.action_durations_mu[branch][index].eq(
                        self.rtlink.o.data
                    )
                ]
                write_cases[mask_addr] = [
                    self.core.actions.action_masks[branch][index].eq(
                        self.rtlink.o.data[:num_outputs]
                    )
                ]
                write_cases[value_addr] = [
                    self.core.actions.action_values[branch][index].eq(
                        self.rtlink.o.data[:num_outputs]
                    )
                ]

        self.sync.rio += If(
            self.rtlink.o.stb & ~self.rtlink.o.address[7],
            Case(self.rtlink.o.address, write_cases),
        )

        action_outputs = Signal(num_outputs)
        experiment_outputs = []
        for bit in range(num_outputs):
            value = self.core.action_output_value[bit]
            if bit == int(ActionOutput.FORT_GATE):
                value = value | self.core.fort_off
            if bit == int(ActionOutput.EXCITATION_GATE):
                value = value | self.core.excitation_enable
            experiment_outputs.append(value)
        self.comb += action_outputs.eq(Cat(*experiment_outputs))

        if simulate or passthrough_sigs is None or output_overrides is not None:
            passthrough = Const(0, num_outputs)
        else:
            passthrough = Cat(*passthrough_sigs)
        self.comb += self.output_signals.eq(Mux(self.enable, action_outputs, passthrough))

        if not simulate and output_overrides is not None:
            for index, (override_en, override_o) in enumerate(output_overrides[:num_outputs]):
                self.comb += [
                    override_en.eq(self.enable),
                    override_o.eq(action_outputs[index]),
                ]
        elif not simulate:
            for index, pad in enumerate(output_pads[:num_outputs]):
                self.specials += Instance(
                    "OBUFDS",
                    i_I=self.output_signals[index],
                    o_O=pad.p,
                    o_OB=pad.n,
                )
            if len(output_pads) == num_outputs + 1:
                self.specials += Instance(
                    "OBUFDS",
                    i_I=self.core.running,
                    o_O=output_pads[-1].p,
                    o_OB=output_pads[-1].n,
                )

        read = Signal()
        read_addr = Signal(8)
        self.sync.rio += [
            If(read, read.eq(0)),
            If(
                self.rtlink.o.stb,
                read.eq(self.rtlink.o.address[7]),
                read_addr.eq(self.rtlink.o.address),
            ),
        ]

        status = Signal(32)
        self.comb += status.eq(
            Cat(
                self.enable,
                self.core.running,
                self.core.success,
                self.core.failed,
                self.core.invalid_config,
            )
        )

        reg_read = Signal(32)
        read_cases = {
            int(AtomPhotonRead.STATUS): [reg_read.eq(status)],
            int(AtomPhotonRead.OUTCOME): [reg_read.eq(self.core.final_outcome)],
            int(AtomPhotonRead.DONE_REASON): [reg_read.eq(self.core.done_reason)],
            int(AtomPhotonRead.ATTEMPTS_COMPLETED): [
                reg_read.eq(self.core.attempts_completed)
            ],
            int(AtomPhotonRead.SPCM0_TIMESTAMP_MU): [
                reg_read.eq(self.core.spcm0_timestamp_mu)
            ],
            int(AtomPhotonRead.SPCM1_TIMESTAMP_MU): [
                reg_read.eq(self.core.spcm1_timestamp_mu)
            ],
            int(AtomPhotonRead.CHOSEN_TIMESTAMP_MU): [
                reg_read.eq(self.core.chosen_timestamp_mu)
            ],
            int(AtomPhotonRead.ATOM_CHECK_COUNTS): [reg_read.eq(0)],
        }
        self.comb += Case(read_addr, read_cases)

        done_result = Signal(32)
        self.comb += done_result.eq(
            Cat(
                self.core.final_outcome,
                self.core.done_reason,
                self.core.attempts_completed,
                self.core.success,
                self.core.failed,
            )
        )
        self.comb += [
            self.rtlink.i.stb.eq(read | self.core.done_stb),
            self.rtlink.i.data.eq(
                Mux(self.core.done_stb, done_result, reg_read)
            ),
        ]

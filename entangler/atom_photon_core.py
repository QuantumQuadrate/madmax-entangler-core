"""Experiment-specific atom-photon parity gateware prototype."""

from __future__ import annotations

import functools
import operator
import typing

from migen import Cat
from migen import FSM
from migen import If
from migen import Module
from migen import Mux
from migen import NextState
from migen import NextValue
from migen import Signal
from migen.fhdl.structure import Constant as Const

from entangler.atom_photon_registers import (
    COARSE_COUNTER_WIDTH,
    FINE_TS_BITS,
    MAX_BRANCH_ACTIONS,
    TIMING_WIDTH,
    BranchPolicy,
    DoneReason,
    PhotonOutcome,
)


NUM_ACTION_OUTPUTS = 8
MIN_VALID_GATE_START_MU = 8


def _or_terms(terms: typing.Sequence[typing.Any]) -> typing.Any:
    if not terms:
        return 0
    return functools.reduce(operator.or_, terms)


def _and_terms(terms: typing.Sequence[typing.Any]) -> typing.Any:
    if not terms:
        return 1
    return functools.reduce(operator.and_, terms)


class PhotonEventDetector(Module):
    """Gate two SPCMs and classify the first-click outcome."""

    def __init__(self, coarse_counter: Signal, spcm0_phy: typing.Any, spcm1_phy: typing.Any):
        self.clear = Signal()
        self.gate_start_mu = Signal(TIMING_WIDTH)
        self.gate_stop_mu = Signal(TIMING_WIDTH)
        self.window_valid = Signal()

        self.spcm0_seen = Signal()
        self.spcm1_seen = Signal()
        self.spcm0_timestamp_mu = Signal(TIMING_WIDTH)
        self.spcm1_timestamp_mu = Signal(TIMING_WIDTH)
        self.chosen_timestamp_mu = Signal(TIMING_WIDTH)
        self.outcome = Signal(max=int(PhotonOutcome.INVALID) + 1)
        self.is_exclusive = Signal()

        # # #

        spcm0_now_mu = Signal(TIMING_WIDTH)
        spcm1_now_mu = Signal(TIMING_WIDTH)
        spcm0_in_window = Signal()
        spcm1_in_window = Signal()

        self.comb += [
            spcm0_now_mu.eq(Cat(spcm0_phy.fine_ts, coarse_counter)),
            spcm1_now_mu.eq(Cat(spcm1_phy.fine_ts, coarse_counter)),
            self.window_valid.eq(
                (self.gate_start_mu >= MIN_VALID_GATE_START_MU)
                & (self.gate_stop_mu > self.gate_start_mu)
            ),
            spcm0_in_window.eq(
                self.window_valid
                & (spcm0_now_mu >= self.gate_start_mu)
                & (spcm0_now_mu <= self.gate_stop_mu)
            ),
            spcm1_in_window.eq(
                self.window_valid
                & (spcm1_now_mu >= self.gate_start_mu)
                & (spcm1_now_mu <= self.gate_stop_mu)
            ),
        ]

        self.sync += [
            If(
                self.clear,
                self.spcm0_seen.eq(0),
                self.spcm1_seen.eq(0),
                self.spcm0_timestamp_mu.eq(0),
                self.spcm1_timestamp_mu.eq(0),
            ).Else(
                If(
                    spcm0_phy.stb & ~self.spcm0_seen & spcm0_in_window,
                    self.spcm0_seen.eq(1),
                    self.spcm0_timestamp_mu.eq(spcm0_now_mu),
                ),
                If(
                    spcm1_phy.stb & ~self.spcm1_seen & spcm1_in_window,
                    self.spcm1_seen.eq(1),
                    self.spcm1_timestamp_mu.eq(spcm1_now_mu),
                ),
            )
        ]

        self.comb += [
            self.outcome.eq(int(PhotonOutcome.NEITHER)),
            self.chosen_timestamp_mu.eq(0),
            self.is_exclusive.eq(
                (self.spcm0_seen & ~self.spcm1_seen)
                | (~self.spcm0_seen & self.spcm1_seen)
            ),
        ]
        self.comb += If(
            self.spcm0_seen & ~self.spcm1_seen,
            self.outcome.eq(int(PhotonOutcome.SPCM0_ONLY)),
            self.chosen_timestamp_mu.eq(self.spcm0_timestamp_mu),
        ).Elif(
            ~self.spcm0_seen & self.spcm1_seen,
            self.outcome.eq(int(PhotonOutcome.SPCM1_ONLY)),
            self.chosen_timestamp_mu.eq(self.spcm1_timestamp_mu),
        ).Elif(
            self.spcm0_seen & self.spcm1_seen,
            self.outcome.eq(int(PhotonOutcome.BOTH)),
        )


class TimestampRelativeActionSequencer(Module):
    """Play branch-specific output actions relative to a photon timestamp."""

    def __init__(
        self,
        coarse_counter: Signal,
        *,
        num_outputs: int = NUM_ACTION_OUTPUTS,
        max_actions: int = MAX_BRANCH_ACTIONS,
    ):
        self.start = Signal()
        self.clear = Signal()
        self.branch = Signal(max=2)
        self.base_timestamp_mu = Signal(TIMING_WIDTH)

        self.action_count = [Signal(max=max_actions + 1) for _ in range(2)]
        self.action_offsets_mu = [
            [Signal(TIMING_WIDTH) for _ in range(max_actions)] for _ in range(2)
        ]
        self.action_durations_mu = [
            [Signal(TIMING_WIDTH) for _ in range(max_actions)] for _ in range(2)
        ]
        self.action_masks = [
            [Signal(num_outputs) for _ in range(max_actions)] for _ in range(2)
        ]
        self.action_values = [
            [Signal(num_outputs) for _ in range(max_actions)] for _ in range(2)
        ]

        self.running = Signal()
        self.done_stb = Signal()
        self.output_enable = Signal(num_outputs)
        self.output_value = Signal(num_outputs)

        # # #

        now_mu = Signal(TIMING_WIDTH)
        selected_count = Signal(max=max_actions + 1)
        done_flags = Signal(max_actions)
        all_done = Signal()
        done_stb_d = Signal()

        self.comb += [
            now_mu.eq(Cat(Const(0, FINE_TS_BITS), coarse_counter)),
            selected_count.eq(Mux(self.branch, self.action_count[1], self.action_count[0])),
        ]

        output_enable_terms = [[] for _ in range(num_outputs)]
        output_value_terms = [[] for _ in range(num_outputs)]
        all_done_terms = []

        for i in range(max_actions):
            offset_mu = Signal(TIMING_WIDTH)
            duration_mu = Signal(TIMING_WIDTH)
            mask = Signal(num_outputs)
            value = Signal(num_outputs)
            start_mu = Signal(TIMING_WIDTH)
            stop_mu = Signal(TIMING_WIDTH)
            enabled = Signal()
            active = Signal()
            expired = Signal()

            self.comb += [
                offset_mu.eq(
                    Mux(
                        self.branch,
                        self.action_offsets_mu[1][i],
                        self.action_offsets_mu[0][i],
                    )
                ),
                duration_mu.eq(
                    Mux(
                        self.branch,
                        self.action_durations_mu[1][i],
                        self.action_durations_mu[0][i],
                    )
                ),
                mask.eq(Mux(self.branch, self.action_masks[1][i], self.action_masks[0][i])),
                value.eq(
                    Mux(self.branch, self.action_values[1][i], self.action_values[0][i])
                ),
                start_mu.eq(self.base_timestamp_mu + offset_mu),
                stop_mu.eq(self.base_timestamp_mu + offset_mu + duration_mu),
                enabled.eq(self.running & (selected_count > i) & (duration_mu != 0)),
                active.eq(enabled & (now_mu >= start_mu) & (now_mu < stop_mu)),
                expired.eq(enabled & (now_mu >= stop_mu)),
            ]

            for bit in range(num_outputs):
                output_enable_terms[bit].append(active & mask[bit])
                output_value_terms[bit].append(active & mask[bit] & value[bit])

            all_done_terms.append((selected_count <= i) | done_flags[i])
            self.sync += If(self.running & expired, done_flags[i].eq(1))

        for bit in range(num_outputs):
            self.comb += [
                self.output_enable[bit].eq(_or_terms(output_enable_terms[bit])),
                self.output_value[bit].eq(_or_terms(output_value_terms[bit])),
            ]

        self.comb += [
            all_done.eq(_and_terms(all_done_terms)),
            self.done_stb.eq(all_done & self.running & ~done_stb_d),
        ]

        self.sync += [
            done_stb_d.eq(all_done & self.running),
            If(
                self.clear,
                self.running.eq(0),
                done_flags.eq(0),
            ).Elif(
                self.start,
                self.running.eq(1),
                done_flags.eq(0),
            ).Elif(self.running & all_done, self.running.eq(0)),
        ]


class AtomPhotonParityCore(Module):
    """Critical-path atom-photon parity sequencer.

    This first implementation covers excitation attempt timing, two-SPCM branch
    detection, timestamp-relative branch actions, retry, and compact results.
    Atom-check and recooling loops are intentionally left for the next layer.
    """

    def __init__(
        self,
        input_phys: typing.Sequence[typing.Any],
        *,
        coarse_counter: typing.Optional[Signal] = None,
        num_action_outputs: int = NUM_ACTION_OUTPUTS,
        max_actions: int = MAX_BRANCH_ACTIONS,
    ):
        if len(input_phys) < 2:
            raise ValueError("AtomPhotonParityCore requires SPCM0 and SPCM1 inputs")

        self.start_stb = Signal()
        self.clear = Signal()

        self.n_attempts = Signal(16)
        self.attempt_period_mu = Signal(TIMING_WIDTH)
        self.fort_off_mu = Signal(TIMING_WIDTH)
        self.fort_on_mu = Signal(TIMING_WIDTH)
        self.excitation_start_mu = Signal(TIMING_WIDTH)
        self.excitation_stop_mu = Signal(TIMING_WIDTH)
        self.photon_gate_start_mu = Signal(TIMING_WIDTH)
        self.photon_gate_stop_mu = Signal(TIMING_WIDTH)
        self.neither_policy = Signal(max=2)
        self.both_policy = Signal(max=2)

        self.running = Signal()
        self.done_stb = Signal()
        self.success = Signal()
        self.failed = Signal()
        self.invalid_config = Signal()
        self.final_outcome = Signal(max=int(PhotonOutcome.INVALID) + 1)
        self.done_reason = Signal(max=int(DoneReason.CLEARED) + 1)
        self.attempt_index = Signal(16)
        self.attempts_completed = Signal(16)
        self.spcm0_timestamp_mu = Signal(TIMING_WIDTH)
        self.spcm1_timestamp_mu = Signal(TIMING_WIDTH)
        self.chosen_timestamp_mu = Signal(TIMING_WIDTH)

        self.fort_off = Signal()
        self.excitation_enable = Signal()
        self.photon_gate_open = Signal()
        self.action_output_enable = Signal(num_action_outputs)
        self.action_output_value = Signal(num_action_outputs)

        self.coarse_counter = (
            coarse_counter
            if coarse_counter is not None
            else Signal(COARSE_COUNTER_WIDTH)
        )

        # # #

        now_mu = Signal(TIMING_WIDTH)
        attempt_start_mu = Signal(TIMING_WIDTH)
        elapsed_mu = Signal(TIMING_WIDTH)
        gate_abs_start_mu = Signal(TIMING_WIDTH)
        gate_abs_stop_mu = Signal(TIMING_WIDTH)
        detector_clear = Signal()
        action_clear = Signal()

        self.comb += [
            now_mu.eq(Cat(Const(0, FINE_TS_BITS), self.coarse_counter)),
            elapsed_mu.eq(now_mu - attempt_start_mu),
            gate_abs_start_mu.eq(attempt_start_mu + self.photon_gate_start_mu),
            gate_abs_stop_mu.eq(attempt_start_mu + self.photon_gate_stop_mu),
            self.invalid_config.eq(
                (self.n_attempts == 0)
                | (self.fort_on_mu <= self.fort_off_mu)
                | (self.excitation_stop_mu <= self.excitation_start_mu)
                | (self.photon_gate_start_mu < MIN_VALID_GATE_START_MU)
                | (self.photon_gate_stop_mu <= self.photon_gate_start_mu)
                | (self.attempt_period_mu <= self.photon_gate_stop_mu)
            ),
        ]

        self.submodules.detector = PhotonEventDetector(
            self.coarse_counter, input_phys[0], input_phys[1]
        )
        self.submodules.actions = TimestampRelativeActionSequencer(
            self.coarse_counter,
            num_outputs=num_action_outputs,
            max_actions=max_actions,
        )

        self.comb += [
            self.detector.clear.eq(detector_clear | self.clear),
            self.detector.gate_start_mu.eq(gate_abs_start_mu),
            self.detector.gate_stop_mu.eq(gate_abs_stop_mu),
            self.actions.clear.eq(action_clear | self.clear),
            self.actions.base_timestamp_mu.eq(self.detector.chosen_timestamp_mu),
            self.actions.branch.eq(
                Mux(self.detector.outcome == int(PhotonOutcome.SPCM1_ONLY), 1, 0)
            ),
            self.spcm0_timestamp_mu.eq(self.detector.spcm0_timestamp_mu),
            self.spcm1_timestamp_mu.eq(self.detector.spcm1_timestamp_mu),
            self.action_output_enable.eq(self.actions.output_enable),
            self.action_output_value.eq(self.actions.output_value),
        ]

        attempt_active = Signal()
        self.comb += [
            self.fort_off.eq(
                attempt_active & (elapsed_mu >= self.fort_off_mu) & (elapsed_mu < self.fort_on_mu)
            ),
            self.excitation_enable.eq(
                attempt_active
                & (elapsed_mu >= self.excitation_start_mu)
                & (elapsed_mu < self.excitation_stop_mu)
            ),
            self.photon_gate_open.eq(
                attempt_active
                & (elapsed_mu >= self.photon_gate_start_mu)
                & (elapsed_mu <= self.photon_gate_stop_mu)
            ),
        ]

        retry_neither = Signal()
        retry_both = Signal()
        attempts_remain = Signal()
        self.comb += [
            attempts_remain.eq((self.attempt_index + 1) < self.n_attempts),
            retry_neither.eq(
                (self.neither_policy == int(BranchPolicy.RETRY)) & attempts_remain
            ),
            retry_both.eq((self.both_policy == int(BranchPolicy.RETRY)) & attempts_remain),
        ]

        self.sync += [
            If(
                self.clear,
                self.coarse_counter.eq(0),
            ).Elif(self.start_stb, self.coarse_counter.eq(0)).Elif(
                self.running, self.coarse_counter.eq(self.coarse_counter + 1)
            )
        ]

        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        self.comb += [
            attempt_active.eq(fsm.ongoing("ATTEMPT")),
            self.done_stb.eq(fsm.ongoing("FINISH")),
        ]

        fsm.act(
            "IDLE",
            detector_clear.eq(1),
            action_clear.eq(1),
            If(
                self.start_stb,
                NextValue(self.running, 1),
                NextValue(self.success, 0),
                NextValue(self.failed, 0),
                NextValue(self.final_outcome, int(PhotonOutcome.NEITHER)),
                NextValue(self.done_reason, int(DoneReason.IDLE)),
                NextValue(self.attempt_index, 0),
                NextValue(self.attempts_completed, 0),
                NextValue(self.chosen_timestamp_mu, 0),
                NextValue(attempt_start_mu, 0),
                If(
                    self.invalid_config,
                    NextValue(self.failed, 1),
                    NextValue(self.final_outcome, int(PhotonOutcome.INVALID)),
                    NextValue(self.done_reason, int(DoneReason.INVALID_CONFIG)),
                    NextState("FINISH"),
                ).Else(NextState("ATTEMPT")),
            ),
        )

        fsm.act(
            "ATTEMPT",
            If(now_mu > gate_abs_stop_mu, NextState("EVALUATE")),
        )

        fsm.act(
            "EVALUATE",
            NextValue(self.attempts_completed, self.attempt_index + 1),
            If(
                self.detector.is_exclusive,
                self.actions.start.eq(1),
                NextValue(self.success, 1),
                NextValue(self.final_outcome, self.detector.outcome),
                NextValue(self.done_reason, int(DoneReason.SUCCESS)),
                NextValue(self.chosen_timestamp_mu, self.detector.chosen_timestamp_mu),
                NextState("ACTIONS"),
            ).Elif(
                self.detector.outcome == int(PhotonOutcome.BOTH),
                If(
                    retry_both,
                    detector_clear.eq(1),
                    NextValue(self.attempt_index, self.attempt_index + 1),
                    NextValue(attempt_start_mu, attempt_start_mu + self.attempt_period_mu),
                    NextState("ATTEMPT"),
                ).Else(
                    NextValue(self.failed, 1),
                    NextValue(self.final_outcome, int(PhotonOutcome.BOTH)),
                    NextValue(
                        self.done_reason,
                        Mux(
                            self.both_policy == int(BranchPolicy.RETRY),
                            int(DoneReason.MAX_ATTEMPTS),
                            int(DoneReason.BOTH),
                        ),
                    ),
                    NextState("FINISH"),
                ),
            ).Else(
                If(
                    retry_neither,
                    detector_clear.eq(1),
                    NextValue(self.attempt_index, self.attempt_index + 1),
                    NextValue(attempt_start_mu, attempt_start_mu + self.attempt_period_mu),
                    NextState("ATTEMPT"),
                ).Else(
                    NextValue(self.failed, 1),
                    NextValue(self.final_outcome, int(PhotonOutcome.NEITHER)),
                    NextValue(
                        self.done_reason,
                        Mux(
                            self.neither_policy == int(BranchPolicy.RETRY),
                            int(DoneReason.MAX_ATTEMPTS),
                            int(DoneReason.NEITHER),
                        ),
                    ),
                    NextState("FINISH"),
                ),
            ),
        )

        fsm.act("ACTIONS", If(self.actions.done_stb, NextState("FINISH")))

        fsm.act(
            "FINISH",
            NextValue(self.running, 0),
            NextState("IDLE"),
        )

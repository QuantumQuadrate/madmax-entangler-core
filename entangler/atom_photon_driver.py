"""Host-side configuration helpers for the atom-photon parity sequencer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from entangler.atom_photon_registers import (
    MAX_BRANCH_ACTIONS,
    TIMING_WIDTH,
    ActionOutput,
    AtomPhotonRead,
    AtomPhotonWrite,
    BranchPolicy,
    action_entry_registers,
)


MIN_PHOTON_GATE_START_MU = 8
MIN_BRANCH_ACTION_OFFSET_MU = 32
MAX_OUTPUT_BITS = 8

try:
    from artiq.coredevice.rtio import rtio_input_data
    from artiq.coredevice.rtio import rtio_input_timestamped_data
    from artiq.coredevice.rtio import rtio_output
    from artiq.language.core import delay_mu
    from artiq.language.core import kernel
    from artiq.language.types import TInt32
    from artiq.language.types import TInt64
    from artiq.language.types import TTuple
except ImportError:  # pragma: no cover - lets host-side tests import without ARTIQ.
    def kernel(function):
        return function

    TInt32 = int
    TInt64 = int

    def TTuple(_types):
        return tuple

    def delay_mu(_duration_mu):
        raise RuntimeError("ARTIQ is required for kernel driver methods")

    def rtio_output(_address, _value):
        raise RuntimeError("ARTIQ is required for kernel driver methods")

    def rtio_input_data(_channel):
        raise RuntimeError("ARTIQ is required for kernel driver methods")

    def rtio_input_timestamped_data(_timeout_mu, _channel):
        raise RuntimeError("ARTIQ is required for kernel driver methods")


class AtomPhotonEntangler:
    """ARTIQ coredevice driver for the atom-photon parity gateware path."""

    kernel_invariants = {
        "core",
        "channel",
        "ref_period_mu",
        "_ADDRESS_CONFIG",
        "_ADDRESS_CONTROL",
        "_ADDRESS_STATUS",
        "_ADDRESS_OUTCOME",
        "_ADDRESS_DONE_REASON",
        "_ADDRESS_ATTEMPTS_COMPLETED",
        "_ADDRESS_SPCM0_TIMESTAMP_MU",
        "_ADDRESS_SPCM1_TIMESTAMP_MU",
        "_ADDRESS_CHOSEN_TIMESTAMP_MU",
    }

    def __init__(self, dmgr, channel, core_device="core"):
        self.core = dmgr.get(core_device)
        self.channel = channel
        self.ref_period_mu = self.core.seconds_to_mu(self.core.coarse_ref_period)
        self._ADDRESS_CONFIG = int(AtomPhotonWrite.CONFIG)
        self._ADDRESS_CONTROL = int(AtomPhotonWrite.CONTROL)
        self._ADDRESS_STATUS = int(AtomPhotonRead.STATUS)
        self._ADDRESS_OUTCOME = int(AtomPhotonRead.OUTCOME)
        self._ADDRESS_DONE_REASON = int(AtomPhotonRead.DONE_REASON)
        self._ADDRESS_ATTEMPTS_COMPLETED = int(AtomPhotonRead.ATTEMPTS_COMPLETED)
        self._ADDRESS_SPCM0_TIMESTAMP_MU = int(AtomPhotonRead.SPCM0_TIMESTAMP_MU)
        self._ADDRESS_SPCM1_TIMESTAMP_MU = int(AtomPhotonRead.SPCM1_TIMESTAMP_MU)
        self._ADDRESS_CHOSEN_TIMESTAMP_MU = int(AtomPhotonRead.CHOSEN_TIMESTAMP_MU)

    @kernel
    def _write(self, addr: TInt32, value: TInt32):
        rtio_output((self.channel << 8) | addr, value)
        delay_mu(self.ref_period_mu)

    @kernel
    def _read(self, addr: TInt32) -> TInt32:
        rtio_output((self.channel << 8) | addr, 0)
        return rtio_input_data(self.channel)

    @kernel
    def write_register(self, addr: TInt32, value: TInt32):
        self._write(addr, value)

    @kernel
    def read_register(self, addr: TInt32) -> TInt32:
        return self._read(addr)

    @kernel
    def set_config(self, enable: TInt32 = 0):
        self._write(self._ADDRESS_CONFIG, enable & 0x1)

    @kernel
    def init(self):
        self.set_config(0)

    @kernel
    def clear(self):
        self._write(self._ADDRESS_CONTROL, 0x2)

    @kernel
    def start(self):
        self._write(self._ADDRESS_CONTROL, 0x1)

    @kernel
    def run_mu(self) -> TTuple([TInt64, TInt32]):
        self.start()
        return rtio_input_timestamped_data(-1, self.channel)

    @kernel
    def get_status(self) -> TInt32:
        return self._read(self._ADDRESS_STATUS)

    @kernel
    def get_outcome(self) -> TInt32:
        return self._read(self._ADDRESS_OUTCOME)

    @kernel
    def get_done_reason(self) -> TInt32:
        return self._read(self._ADDRESS_DONE_REASON)

    @kernel
    def get_attempts_completed(self) -> TInt32:
        return self._read(self._ADDRESS_ATTEMPTS_COMPLETED)

    @kernel
    def get_spcm0_timestamp_mu(self) -> TInt32:
        return self._read(self._ADDRESS_SPCM0_TIMESTAMP_MU)

    @kernel
    def get_spcm1_timestamp_mu(self) -> TInt32:
        return self._read(self._ADDRESS_SPCM1_TIMESTAMP_MU)

    @kernel
    def get_chosen_timestamp_mu(self) -> TInt32:
        return self._read(self._ADDRESS_CHOSEN_TIMESTAMP_MU)


@dataclass(frozen=True)
class BranchAction:
    """One timestamp-relative action-table entry."""

    offset_mu: int
    duration_mu: int
    output_mask: int
    output_value: int

    @classmethod
    def pulse(cls, output: ActionOutput, offset_mu: int, duration_mu: int) -> "BranchAction":
        """Create an active-high pulse action for one output bit."""

        bit = 1 << int(output)
        return cls(
            offset_mu=offset_mu,
            duration_mu=duration_mu,
            output_mask=bit,
            output_value=bit,
        )


@dataclass(frozen=True)
class AtomCheckConfig:
    """Reserved atom-check/recooling configuration surface.

    The first gateware prototype does not implement the counter threshold loop
    yet, but the host API keeps these fields explicit so the migration path is
    visible.
    """

    enabled: bool = False
    gate_start_mu: int = 0
    gate_stop_mu: int = 0
    threshold_count: int = 0
    recooling_enabled: bool = False
    recooling_start_mu: int = 0
    recooling_stop_mu: int = 0


@dataclass(frozen=True)
class AtomPhotonParityConfig:
    """Experiment-shaped configuration for the parity sequencer."""

    n_excitation_attempts: int
    attempt_period_mu: int
    fort_off_mu: int
    fort_on_mu: int
    excitation_start_mu: int
    excitation_stop_mu: int
    photon_gate_start_mu: int
    photon_gate_stop_mu: int
    branch0_actions: tuple[BranchAction, ...] = field(default_factory=tuple)
    branch1_actions: tuple[BranchAction, ...] = field(default_factory=tuple)
    neither_policy: BranchPolicy = BranchPolicy.RETRY
    both_policy: BranchPolicy = BranchPolicy.RETRY
    atom_check: AtomCheckConfig = field(default_factory=AtomCheckConfig)

    def validate(self) -> None:
        """Reject configurations that the first gateware path cannot execute."""

        _require_uint("n_excitation_attempts", self.n_excitation_attempts, 16)
        if self.n_excitation_attempts == 0:
            raise ValueError("n_excitation_attempts must be non-zero")

        for name in (
            "attempt_period_mu",
            "fort_off_mu",
            "fort_on_mu",
            "excitation_start_mu",
            "excitation_stop_mu",
            "photon_gate_start_mu",
            "photon_gate_stop_mu",
        ):
            _require_uint(name, getattr(self, name), TIMING_WIDTH)

        if self.fort_on_mu <= self.fort_off_mu:
            raise ValueError("FORT on time must be after FORT off time")
        if self.excitation_stop_mu <= self.excitation_start_mu:
            raise ValueError("excitation stop must be after excitation start")
        if self.photon_gate_start_mu < MIN_PHOTON_GATE_START_MU:
            raise ValueError("photon gate must start at least 8 mu after attempt start")
        if self.photon_gate_stop_mu <= self.photon_gate_start_mu:
            raise ValueError("photon gate stop must be after gate start")
        if self.attempt_period_mu <= self.photon_gate_stop_mu:
            raise ValueError("attempt period must exceed photon gate stop")

        for branch, actions in enumerate((self.branch0_actions, self.branch1_actions)):
            if len(actions) > MAX_BRANCH_ACTIONS:
                raise ValueError("too many actions in branch %d" % branch)
            min_action_offset_mu = (
                self.photon_gate_stop_mu
                - self.photon_gate_start_mu
                + MIN_BRANCH_ACTION_OFFSET_MU
            )
            for index, action in enumerate(actions):
                _validate_action(branch, index, action, min_action_offset_mu)

        _validate_atom_check(self.atom_check)

    def iter_register_writes(self) -> Iterable[tuple[int, int]]:
        """Yield register writes for the future RTIO PHY wrapper."""

        self.validate()
        yield int(AtomPhotonWrite.N_ATTEMPTS), self.n_excitation_attempts
        yield int(AtomPhotonWrite.ATTEMPT_PERIOD_MU), self.attempt_period_mu
        yield int(AtomPhotonWrite.FORT_OFF_MU), self.fort_off_mu
        yield int(AtomPhotonWrite.FORT_ON_MU), self.fort_on_mu
        yield int(AtomPhotonWrite.EXCITATION_START_MU), self.excitation_start_mu
        yield int(AtomPhotonWrite.EXCITATION_STOP_MU), self.excitation_stop_mu
        yield int(AtomPhotonWrite.PHOTON_GATE_START_MU), self.photon_gate_start_mu
        yield int(AtomPhotonWrite.PHOTON_GATE_STOP_MU), self.photon_gate_stop_mu
        policies = int(self.neither_policy) | (int(self.both_policy) << 4)
        yield int(AtomPhotonWrite.BRANCH_POLICIES), policies
        yield int(AtomPhotonWrite.ATOM_CHECK_CONTROL), int(self.atom_check.enabled)
        yield int(AtomPhotonWrite.ATOM_CHECK_GATE_START_MU), self.atom_check.gate_start_mu
        yield int(AtomPhotonWrite.ATOM_CHECK_GATE_STOP_MU), self.atom_check.gate_stop_mu
        yield int(AtomPhotonWrite.ATOM_CHECK_THRESHOLD), self.atom_check.threshold_count
        yield int(AtomPhotonWrite.RECOOLING_START_MU), self.atom_check.recooling_start_mu
        yield int(AtomPhotonWrite.RECOOLING_STOP_MU), self.atom_check.recooling_stop_mu
        yield int(AtomPhotonWrite.BRANCH0_ACTION_COUNT), len(self.branch0_actions)
        yield int(AtomPhotonWrite.BRANCH1_ACTION_COUNT), len(self.branch1_actions)

        for branch, actions in enumerate((self.branch0_actions, self.branch1_actions)):
            for index in range(MAX_BRANCH_ACTIONS):
                offset_addr, duration_addr, mask_addr, value_addr = action_entry_registers(
                    branch, index
                )
                if index < len(actions):
                    action = actions[index]
                    yield offset_addr, action.offset_mu
                    yield duration_addr, action.duration_mu
                    yield mask_addr, action.output_mask
                    yield value_addr, action.output_value
                else:
                    yield offset_addr, 0
                    yield duration_addr, 0
                    yield mask_addr, 0
                    yield value_addr, 0


def microwave_mapping_actions(
    mw_start_offset_mu: int,
    mw_duration_mu: int,
    *,
    rf_start_offset_mu: int | None = None,
    rf_duration_mu: int = 0,
    dds_profile_offset_mu: int | None = None,
    blow_away_offset_mu: int | None = None,
    blow_away_duration_mu: int = 0,
    parity_readout_offset_mu: int | None = None,
    parity_readout_duration_mu: int = 0,
) -> tuple[BranchAction, ...]:
    """Build the common post-click action sequence from the experiment code."""

    actions: list[BranchAction] = [
        BranchAction.pulse(ActionOutput.MW_SWITCH, mw_start_offset_mu, mw_duration_mu)
    ]
    if dds_profile_offset_mu is not None:
        actions.append(
            BranchAction.pulse(ActionOutput.DDS_PROFILE_TRIGGER, dds_profile_offset_mu, 8)
        )
    if rf_start_offset_mu is not None and rf_duration_mu > 0:
        actions.append(
            BranchAction.pulse(ActionOutput.RF_SWITCH, rf_start_offset_mu, rf_duration_mu)
        )
    if blow_away_offset_mu is not None and blow_away_duration_mu > 0:
        actions.append(
            BranchAction.pulse(
                ActionOutput.BLOW_AWAY, blow_away_offset_mu, blow_away_duration_mu
            )
        )
    if parity_readout_offset_mu is not None and parity_readout_duration_mu > 0:
        actions.append(
            BranchAction.pulse(
                ActionOutput.PARITY_READOUT,
                parity_readout_offset_mu,
                parity_readout_duration_mu,
            )
        )
    return tuple(actions)


def _require_uint(name: str, value: int, width: int) -> None:
    if not isinstance(value, int):
        raise TypeError("%s must be an int" % name)
    if value < 0 or value >= (1 << width):
        raise ValueError("%s outside unsigned %d-bit range" % (name, width))


def _validate_action(
    branch: int,
    index: int,
    action: BranchAction,
    min_action_offset_mu: int,
) -> None:
    for name in ("offset_mu", "duration_mu", "output_mask", "output_value"):
        _require_uint(
            "branch%d action%d %s" % (branch, index, name),
            getattr(action, name),
            TIMING_WIDTH,
        )
    if action.offset_mu < min_action_offset_mu:
        raise ValueError(
            "branch%d action%d offset is below the exclusive-branch reaction limit"
            % (branch, index),
        )
    if action.duration_mu == 0:
        raise ValueError("branch%d action%d duration must be non-zero" % (branch, index))
    max_mask = (1 << MAX_OUTPUT_BITS) - 1
    if action.output_mask & ~max_mask:
        raise ValueError("branch%d action%d output mask uses unavailable bits" % (branch, index))
    if action.output_value & ~action.output_mask:
        raise ValueError("branch%d action%d value sets bits outside mask" % (branch, index))


def _validate_atom_check(atom_check: AtomCheckConfig) -> None:
    for name in (
        "gate_start_mu",
        "gate_stop_mu",
        "threshold_count",
        "recooling_start_mu",
        "recooling_stop_mu",
    ):
        _require_uint("atom_check %s" % name, getattr(atom_check, name), TIMING_WIDTH)
    if atom_check.enabled and atom_check.gate_stop_mu <= atom_check.gate_start_mu:
        raise ValueError("atom-check gate stop must be after start")
    if (
        atom_check.recooling_enabled
        and atom_check.recooling_stop_mu <= atom_check.recooling_start_mu
    ):
        raise ValueError("recooling stop must be after start")

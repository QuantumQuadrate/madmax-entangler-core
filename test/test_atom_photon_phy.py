"""Test the atom-photon parity RTIO PHY wrapper."""

import os
import sys

import migen

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

from atom_photon_phytester import (  # noqa: E402 pylint: disable=import-error
    AtomPhotonPhyTestHarness,
)

from entangler.atom_photon_driver import (  # noqa: E402
    AtomPhotonParityConfig,
    BranchAction,
)
from entangler.atom_photon_registers import (  # noqa: E402
    ActionOutput,
    AtomPhotonRead,
    AtomPhotonWrite,
    PhotonOutcome,
)


CLOCKS = {"sys": 8, "rio": 8, "rio_phy": 8}
NO_EVENT_MU = (1 << 28) * 8


def _config_writes():
    config = AtomPhotonParityConfig(
        n_excitation_attempts=1,
        attempt_period_mu=128,
        fort_off_mu=0,
        fort_on_mu=72,
        excitation_start_mu=8,
        excitation_stop_mu=24,
        photon_gate_start_mu=16,
        photon_gate_stop_mu=64,
        branch0_actions=(
            BranchAction.pulse(ActionOutput.MW_SWITCH, 80, 16),
        ),
        branch1_actions=(
            BranchAction.pulse(ActionOutput.RF_SWITCH, 80, 16),
        ),
    )
    return tuple(config.iter_register_writes())


def test_atom_photon_phy_register_run_and_readout(request):
    dut = AtomPhotonPhyTestHarness()

    def bench():
        for address, data in _config_writes():
            yield from dut.write(address, data)
        yield from dut.write(int(AtomPhotonWrite.CONFIG), 1)
        yield from dut.set_event_times([32, NO_EVENT_MU])
        yield from dut.write(int(AtomPhotonWrite.CONTROL), 1)

        samples = []
        done_data = None
        for _ in range(80):
            now_mu = (yield dut.core.core.coarse_counter) << 3
            outputs = yield dut.core.output_signals
            if outputs:
                samples.append((now_mu, outputs))
            if (yield dut.core.rtlink.i.stb):
                done_data = yield dut.core.rtlink.i.data
                break
            yield

        assert done_data is not None
        assert (done_data & 0x7) == int(PhotonOutcome.SPCM0_ONLY)
        assert any(
            time_mu == 112 and outputs & (1 << int(ActionOutput.MW_SWITCH))
            for time_mu, outputs in samples
        )

        outcome = [0]
        chosen_ts = [0]
        attempts = [0]
        yield from dut.read(int(AtomPhotonRead.OUTCOME), outcome)
        yield from dut.read(int(AtomPhotonRead.CHOSEN_TIMESTAMP_MU), chosen_ts)
        yield from dut.read(int(AtomPhotonRead.ATTEMPTS_COMPLETED), attempts)
        assert outcome[0] == int(PhotonOutcome.SPCM0_ONLY)
        assert chosen_ts[0] == 32
        assert attempts[0] == 1

    migen.run_simulation(
        dut,
        bench(),
        vcd_name=request.node.name + ".vcd",
        clocks=CLOCKS,
    )

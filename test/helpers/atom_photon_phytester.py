"""RTIO PHY test harness for the atom-photon parity entangler."""

import logging
import os
import sys
import typing

import migen

sys.path.append(os.path.dirname(__file__))

from gateware_utils import MockPhy  # noqa: E402 pylint: disable=import-error
from gateware_utils import rtio_output_event  # noqa: E402 pylint: disable=import-error

import entangler.atom_photon_phy  # noqa: E402
from entangler.config import settings  # noqa: E402

_LOGGER = logging.getLogger(__name__)


class AtomPhotonPhyTestHarness(migen.Module):
    """Mock SPCM inputs and RTIO writes around the atom-photon PHY."""

    def __init__(self):
        self.counter = migen.Signal(32)
        self.input_phys = [
            MockPhy(self.counter) for _ in range(settings.NUM_ENTANGLER_INPUT_SIGNALS)
        ]
        self.submodules += self.input_phys
        self.submodules.core = entangler.atom_photon_phy.AtomPhotonParity(
            core_link_pads=None,
            output_pads=None,
            passthrough_sigs=None,
            input_phys=self.input_phys,
            reference_phy=None,
            simulate=True,
        )
        self.comb += self.counter.eq(self.core.core.coarse_counter)

    def write(self, address: int, data: int):
        _LOGGER.debug("Writing atom-photon register 0x%x = 0x%x", address, data)
        yield from rtio_output_event(self.core.rtlink, address, data)
        yield

    def read(self, address: int, data_ref: list):
        yield from rtio_output_event(self.core.rtlink, address, 0)
        yield
        data_ref[0] = yield self.core.rtlink.i.data

    def set_event_times(self, event_times_mu: typing.Sequence[int]):
        for index, event_time_mu in enumerate(event_times_mu):
            yield self.input_phys[index].t_event.eq(event_time_mu)

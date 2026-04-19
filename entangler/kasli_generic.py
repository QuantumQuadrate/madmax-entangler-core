"""Add support for the Entangler to the generic Kasli builder.

Effectively adds :mod:`entangler` to kasli_generic builder
(artiq/gateware/kasli_generic.py) and the EEM module
(artiq/gateware/eem.py).
"""
import json
import logging
import pathlib
import typing

import artiq.gateware.eem as eem_mod
import artiq.gateware.rtio as rtio
import mergedeep
from artiq import __version__ as _artiq_version_str
from artiq.gateware.rtio.phy import ttl_serdes_7series
from artiq.gateware.rtio.phy import ttl_simple
from migen import Signal
from migen.build.generic_platform import ConstraintError
from migen.build.generic_platform import IOStandard
from migen.build.generic_platform import Pins
from migen.build.generic_platform import Subsignal

import entangler.phy
from entangler.config import settings as entangler_settings
from entangler.gateware.io_mapping import DIO_INPUT_INDICES
from entangler.gateware.io_mapping import DIO_OUTPUT_INDICES
from entangler.gateware.io_mapping import PhysicalTtlChannel

_LOGGER = logging.getLogger(__name__)
# packaging.version.parse() preferred, but the ARTIQ version is not PEP440 compliant
_ARTIQ_MAJOR_VERSION = int(_artiq_version_str.split(".")[0])

if _ARTIQ_MAJOR_VERSION >= 6:
    from artiq.gateware.rtio.phy import edge_counter

    EDGE_COUNTER_CLS = edge_counter.SimpleEdgeCounter
else:
    EDGE_COUNTER_CLS = None

if _ARTIQ_MAJOR_VERSION >= 8:
    import artiq.gateware.targets.kasli as kasligen
else:
    import artiq.gateware.targets.kasli_generic as kasligen



def peripheral_entangler(module, peripheral: typing.Dict[str, list], **kwargs):
    """Add an Ion-Photon entangling gateware device to an ARTIQ SoC.

    Expected format:
        {
            "type": "entangler",
            "ports": [list of ints],
            {OPTIONAL} "uses_reference": bool,
            {OPTIONAL} "running_output": bool
            {OPTIONAL} "link_eem": int,
            {OPTIONAL} "interface_on_lower": bool,
            {OPTIONAL} "edge_counter": bool,
        }

    More details in :class:`EntanglerEEM`.
    """
    using_ref = peripheral.get("uses_reference", False)
    running_signal = peripheral.get("running_output", False)
    num_inputs = entangler_settings.NUM_ENTANGLER_INPUT_SIGNALS
    num_outputs = entangler_settings.NUM_OUTPUT_CHANNELS
    if using_ref:
        # add reference
        num_inputs += 1
    if running_signal:
        num_outputs += 1

    num_eem = len(peripheral["ports"]) + (
        1 if peripheral.get("link_eem") is not None else 0
    )
    if peripheral.get("link_eem") is not None:
        # Using inter-Kasli/Entangler communication
        num_link_pins = 5 if using_ref else 4
    else:
        num_link_pins = 0

    if (num_eem * 8) < num_inputs + num_outputs + num_link_pins:
        _LOGGER.warning(
            "Maybe insufficient number of I/O EEM boards. "
            "Must use Interface to get sufficient number, or another DIO EEM. "
            "Expecting %i total I/O",
            num_inputs + num_outputs + num_link_pins,
        )
    _LOGGER.debug("Adding entangler to Kasli. Params: %s", peripheral)
    EntanglerEEM.add_std(
        module,
        eem_dio=peripheral["ports"],
        eem_interface=peripheral.get("link_eem"),
        uses_reference=using_ref,
        running_output=running_signal,
        interface_on_lower=peripheral.get("interface_on_lower", True),
        edge_counter_cls=EDGE_COUNTER_CLS if peripheral.get("edge_counter") else None
    )


def _add_eem_to_artiq_build(artiq_version: int) -> None:
    """Patch the EEM into the ARTIQ Kasli build process"""
    if artiq_version >= 6:
        import artiq.coredevice.jsondesc as artiq_jsondesc
        import artiq.gateware.eem_7series as eem_7series

        # add entangler processor to the Kasli EEM JSON processors
        eem_7series.peripheral_processors["entangler"] = peripheral_entangler

        # merge Entangler Schema into default ARTIQ schema
        mergedeep.merge(
            artiq_jsondesc.schema,
            json.loads(
                pathlib.Path(__file__)
                .with_name("entangler_eem.schema.json")
                .read_text()
            ),
            strategy=mergedeep.Strategy.TYPESAFE_ADDITIVE,
        )
    elif artiq_version == 5:
        try:
            kasligen.peripheral_processors["entangler"] = peripheral_entangler
        except AttributeError as exc:
            raise ImportError(
                "Likely outdated ARTIQ version. Check your ARTIQ version includes PR #1426"
            ) from exc
    else:
        raise NotImplementedError(
            f"Entangler build via Kasli not (yet) supported for ARTIQ {_artiq_version_str}"
        )


if _ARTIQ_MAJOR_VERSION >= 6:
    _default_iostandard = eem_mod.default_iostandard
else:
    _default_iostandard = "LVDS_25"  # ARTIQ 5


# pylint: disable=protected-access
class EntanglerEEM(eem_mod._EEM):
    """Define the pins and gateware/logic used by the Entangler.

    If you are using this extension, you should NOT use the corresponding EEM(s)
    elsewhere (e.g. as DIO).
    """

    @staticmethod
    def io(
            eem_dio: typing.Sequence[int],
            eem_interface: int = None,
            uses_reference: bool = False,
            interface_on_lower: bool = True,
            iostandard: typing.Union[str, IOStandard] = _default_iostandard,
    ) -> typing.Sequence["Pad_Assignments"]:
        """Define the IO pins used by the Entangler device.

        Args:
            eem_interface (Optional[int]): An optional EEM for interfacing between
                distributed Entanglers (on separate Kasli).
                Set to None for no interface.
            eem_dio (Sequence[int]): EEM numbers for the DIO cards to be used by
                the Entangler. Should be <= (num_inputs + num_outputs, in
                ``settings.toml``). Must have at least one.
            uses_reference (bool): If you are using a reference signal/trigger
                to the Entangler. Defaults to False.
            interface_on_lower (bool): If not using a reference, you need less
                interface pins, which this supports by assigning half of one
                I/O bank (=4 pins) to Interface, and other half to DIO.
                This selects whether the lower (0-3) or upper (4-7) pins should
                be Interface. Others will be DIO.
            iostandard (str): Defines the voltage/communication standard for the pins.
                Defaults to differential ("LVDS_25").

        Returns:
            Sequence["Pad_Assignments"]: Pins meant for defining an EEM platform
            extension.
            Each consists of a connector/bus name, pin name, Subsignals, and other
            parameters like IO Standards.
            Similar to Xilinx/Altera pin config files (``*.ucf``).

        """
        ios = []
        if not isinstance(eem_dio, list):
            eem_dio = [eem_dio]
        for eem in eem_dio:
            ios.extend(eem_mod.DIO.io(eem, iostandard))
        if eem_interface is not None:
            if not uses_reference:
                num_interface_pads = 4
                if interface_on_lower:
                    pad_range = list(range(0, 4))
                    dio_range = list(range(4, 8))
                else:
                    pad_range = list(range(4, 8))
                    dio_range = list(range(0, 4))
            else:
                # doesn't give lower/upper option for reference, just start at 0
                num_interface_pads = 5
                pad_range = list(range(num_interface_pads))
                dio_range = list(range(num_interface_pads, 8))

            _LOGGER.debug(
                "Creating inter-Kasli Entangler state machine interface on "
                "EEM %i, using %i pads (%s)",
                eem_interface,
                num_interface_pads,
                pad_range,
            )
            # pylint: disable=protected-access
            if_io = [
                (
                    "if{}".format(eem_interface),
                    i,
                    Subsignal("p", Pins(eem_mod._eem_pin(eem_interface, i, "p"))),
                    Subsignal("n", Pins(eem_mod._eem_pin(eem_interface, i, "n"))),
                    IOStandard(iostandard),
                )
                for i in pad_range
            ]
            if len(dio_range) != 0:
                # populate remainder with DIO
                if_io.extend(
                    [
                        (
                            "dio{}".format(eem_interface),
                            i,
                            Subsignal(
                                "p",
                                Pins(eem_mod._eem_pin(eem_interface, real_pin, "p")),
                            ),
                            Subsignal(
                                "n",
                                Pins(eem_mod._eem_pin(eem_interface, real_pin, "n")),
                            ),
                            IOStandard(iostandard),
                        )
                        for i, real_pin in enumerate(dio_range)
                    ]
                )
            ios.extend(if_io)
        else:
            _LOGGER.debug("NOT using inter-Kasli Entangler interface")
        return ios

    @classmethod
    def add_std(
            cls,
            target: "MiniSoC",  # noqa: F821
            eem_dio: typing.Sequence[int],
            eem_interface: typing.Optional[int] = None,
            uses_reference: bool = False,
            running_output: bool = False,
            interface_on_lower: bool = True,
            edge_counter_cls: typing.Optional[typing.Type[EDGE_COUNTER_CLS]] = None
    ):
        """Add an Entangler PHY to a Kasli gateware module.

        Args:
            target (Module): The gateware module the Entangler will be added to.
            eem_dio (typing.Sequence[int]): A list of EEM ports that are connected
                to DIO boards, which are used for the inputs & outputs from the
                Entangler.
            eem_interface (typing.Optional[int]): The EEM number where the
                inter-Entangler interface pins will be located.
                Should be connected to a DIO board.
                If set to None, assumes the Entangler is standalone (no remote
                Entangler on a different Kasli) and does not instantiate interface.
            uses_reference (bool, optional): If the Entangler PHY is designed
                to be used in conjunction with a reference trigger/signal.
                For example, if the entanglement can only be generated relative
                to a pulsed laser (as in Oxford). Defaults to False.
            running_output (bool, optional): If the Entangler PHY should output
                an "Is Running?" status signal on the last output channel.
                Defaults to False.
            interface_on_lower (bool, optional): See :meth:`io` for details.
                Basically, if no reference is used, should the 4 pins for
                communication be on the lower or upper half of the DIO bank.
                Defaults to True.
            edge_counter_cls (optional): Add edge counters to input pints.
                Defaults to no edge counters.

        Note:
            Physical DIO routing follows a fixed split on each EEM bank:
            ``dio[*][0:4]`` are treated as inputs and ``dio[*][4:8]`` as outputs.
            Entangler/general inputs (and the optional reference input) are reserved
            from the input pool, while entangler outputs (and the optional running
            output) are reserved from the output pool. RTIO channels are still
            created in the traditional order of outputs first and inputs second so
            the existing driver/DDB channel numbering remains unchanged.

            Built liberally off Oxford's draft EEM code, though greatly extended.
        """
        cls.add_extension(
            target,
            eem_dio,
            eem_interface=eem_interface,
            uses_reference=uses_reference,
            interface_on_lower=interface_on_lower,
        )

        if _ARTIQ_MAJOR_VERSION >= 6:
            io_class = {
                "input": ttl_serdes_7series.InOut_8X,
                "output": ttl_simple.Output,
            }
        else:
            io_class = {
                "input": ttl_serdes_7series.Input_8X,
                "output": ttl_simple.Output,
            }
        num_outputs = entangler_settings.NUM_OUTPUT_CHANNELS
        num_entangler_inputs = entangler_settings.NUM_ENTANGLER_INPUT_SIGNALS
        num_generic_inputs = entangler_settings.NUM_GENERIC_INPUT_SIGNALS
        num_total_inputs = num_entangler_inputs + num_generic_inputs
        if uses_reference:
            num_entangler_inputs += 1
        num_running_outputs = 1 if running_output else 0
        num_if_pins = 5 if uses_reference else 4
        needed_inputs = num_total_inputs + (1 if uses_reference else 0)
        needed_outputs = num_outputs + num_running_outputs

        def _pad_label(eem: int, physical_index: int) -> str:
            return "dio{}[{}]".format(eem, physical_index)

        port_positions = {eem: port_index for port_index, eem in enumerate(eem_dio)}

        def _physical_ttl_channel(
                eem: int, physical_index: int, direction: str
        ) -> typing.Optional[PhysicalTtlChannel]:
            if eem not in port_positions:
                return None
            return PhysicalTtlChannel(
                port_index=port_positions[eem],
                eem_port=eem,
                physical_index=physical_index,
                direction=direction,
            )

        def _exported_name(eem: int, physical_index: int, direction: str) -> str:
            physical_ttl = _physical_ttl_channel(eem, physical_index, direction)
            if physical_ttl is None:
                return "<not exported by standalone DDB>"
            return physical_ttl.exported_name

        def _request_pad(
                eem: int, resource_index: int, physical_index: int
        ) -> typing.Tuple[typing.Any, int, int]:
            return (
                target.platform.request("dio{}".format(eem), resource_index),
                eem,
                physical_index,
            )

        input_pad_pool = []
        output_pad_pool = []
        for eem in eem_dio:
            input_pad_pool.extend(
                _request_pad(eem, i, i) for i in DIO_INPUT_INDICES
            )
            output_pad_pool.extend(
                _request_pad(eem, i, i) for i in DIO_OUTPUT_INDICES
            )

        if eem_interface is not None:
            if uses_reference:
                interface_dio_map = list(enumerate(range(num_if_pins, 8)))
            elif interface_on_lower:
                interface_dio_map = list(enumerate(DIO_OUTPUT_INDICES))
            else:
                interface_dio_map = list(enumerate(DIO_INPUT_INDICES))

            added_interface_inputs = 0
            added_interface_outputs = 0
            try:
                for resource_index, physical_index in interface_dio_map:
                    pad_entry = _request_pad(
                        eem_interface, resource_index, physical_index
                    )
                    if physical_index in DIO_INPUT_INDICES:
                        input_pad_pool.append(pad_entry)
                        added_interface_inputs += 1
                    else:
                        output_pad_pool.append(pad_entry)
                        added_interface_outputs += 1
            except ConstraintError:
                _LOGGER.debug(
                    "Added %i input pads and %i output pads from EEM_interface %i",
                    added_interface_inputs,
                    added_interface_outputs,
                    eem_interface,
                )
            else:
                _LOGGER.debug(
                    "Added %i input pads and %i output pads from EEM_interface %i",
                    added_interface_inputs,
                    added_interface_outputs,
                    eem_interface,
                )

        _LOGGER.info(
            "Found %i input pads and %i output pads for Entangler allocation",
            len(input_pad_pool),
            len(output_pad_pool),
        )
        _LOGGER.debug(
            "Input pad pool: %s",
            ", ".join(_pad_label(eem, i) for _, eem, i in input_pad_pool)
            or "<none>",
        )
        _LOGGER.debug(
            "Output pad pool: %s",
            ", ".join(_pad_label(eem, i) for _, eem, i in output_pad_pool)
            or "<none>",
        )
        if needed_inputs > len(input_pad_pool):
            _LOGGER.error(
                "Trying to allocate more input pins (%i) than provided (%i)",
                needed_inputs,
                len(input_pad_pool),
            )
        if needed_outputs > len(output_pad_pool):
            _LOGGER.error(
                "Trying to allocate more output pins (%i) than provided (%i)",
                needed_outputs,
                len(output_pad_pool),
            )
        if needed_inputs > len(input_pad_pool) or needed_outputs > len(output_pad_pool):
            raise ValueError("Insufficient DIO pads for requested Entangler I/O")

        _LOGGER.debug(
            "Num Outputs: %d, Num Inputs: %d (%d entangler), # Input Pads: %d, # Output Pads: %d",
            num_outputs,
            num_total_inputs,
            num_entangler_inputs,
            len(input_pad_pool),
            len(output_pad_pool),
        )
        input_pads_iter = iter(input_pad_pool)
        output_pads_iter = iter(output_pad_pool)

        allocated_input_pads = [next(input_pads_iter) for _ in range(num_total_inputs)]
        reference_pad = next(input_pads_iter) if uses_reference else None
        allocated_output_pads = [
            next(output_pads_iter) for _ in range(num_outputs)
        ]
        running_output_pad = next(output_pads_iter) if running_output else None

        # Reserve input pads from the detector side first, then assign outputs from
        # the output-side pool while keeping legacy RTIO channel numbering unchanged.
        _LOGGER.debug(
            "Allocated input pads: %s",
            ", ".join(_pad_label(eem, i) for _, eem, i in allocated_input_pads)
            or "<none>",
        )
        if reference_pad is not None:
            _LOGGER.debug(
                "Allocated reference pad: %s",
                _pad_label(reference_pad[1], reference_pad[2]),
            )
        _LOGGER.debug(
            "Allocated output pads: %s",
            ", ".join(_pad_label(eem, i) for _, eem, i in allocated_output_pads)
            or "<none>",
        )
        if running_output_pad is not None:
            _LOGGER.debug(
                "Allocated running-output pad: %s",
                _pad_label(running_output_pad[1], running_output_pad[2]),
            )

        # *** Create PHYs for outputs then inputs (then reference, opt) ***
        output_pads = []
        output_sigs = [Signal() for _ in range(num_outputs)]
        # Assign Entangler outputs to pads, create PHYs
        output_rtio_channels = []
        for i, (pads, eem, physical_index) in enumerate(allocated_output_pads):
            output_pads.append(pads)
            phy = io_class["output"](output_sigs[i])
            target.submodules += phy
            target.rtio_channels.append(rtio.Channel.from_phy(phy))
            output_rtio_channels.append(len(target.rtio_channels) - 1)
            exported_name = _exported_name(eem, physical_index, "output")
            _LOGGER.debug(
                "Assigned Output[%i] to %s on RTIO channel %i",
                i,
                _pad_label(eem, physical_index),
                output_rtio_channels[-1],
            )
            _LOGGER.info(
                "Entangler output[%i]: %s -> RTIO channel %i -> exported as %s",
                i,
                _pad_label(eem, physical_index),
                output_rtio_channels[-1],
                exported_name,
            )
        if output_rtio_channels:
            _LOGGER.info(
                "RTIO Channels %i -> %i configured as Outputs",
                output_rtio_channels[0],
                output_rtio_channels[-1],
            )
        if running_output_pad is not None:
            # processing will be taken care of in EntanglerCore
            pads, eem, physical_index = running_output_pad
            output_pads.append(pads)
            _LOGGER.info(
                "Assigned running output to %s",
                _pad_label(eem, physical_index),
            )

        # Create specified # of inputs, add them to list for Entangler creation.
        input_phys = []
        input_rtio_channels = []
        edge_counter_channels = []
        for i, (pads, eem, physical_index) in enumerate(allocated_input_pads):
            if eem == eem_interface:
                _LOGGER.info(
                    "Assigning Input[%i] to Interface Board (%s)",
                    i,
                    _pad_label(eem, physical_index),
                )
            phy = io_class["input"](pads.p, pads.n)
            target.submodules += phy
            # only add num_entangler_inputs -> input_phys -> Entanglercore
            if i < num_entangler_inputs:
                input_phys.append(phy.rtlink.i)
            target.rtio_channels.append(rtio.Channel.from_phy(phy))
            input_rtio_channels.append(len(target.rtio_channels) - 1)
            exported_name = _exported_name(eem, physical_index, "input")
            _LOGGER.debug(
                "Assigned Input[%i] to %s on RTIO channel %i",
                i,
                _pad_label(eem, physical_index),
                input_rtio_channels[-1],
            )
            _LOGGER.info(
                "Entangler input[%i]: %s -> RTIO channel %i -> exported as %s",
                i,
                _pad_label(eem, physical_index),
                input_rtio_channels[-1],
                exported_name,
            )

            if edge_counter_cls is not None:
                state = getattr(phy, "input_state", None)
                if state is not None:
                    counter = edge_counter_cls(state)
                    target.submodules += counter
                    target.rtio_channels.append(rtio.Channel.from_phy(counter))
                    edge_counter_channels.append(len(target.rtio_channels) - 1)
                    _LOGGER.info(
                        "Entangler input[%i] counter: %s -> RTIO channel %i -> exported as %s_counter",
                        i,
                        _pad_label(eem, physical_index),
                        edge_counter_channels[-1],
                        exported_name,
                    )

        if input_rtio_channels:
            _LOGGER.info(
                "RTIO Channels %i -> %i configured as Inputs (first %i entangle-able)",
                input_rtio_channels[0],
                input_rtio_channels[-1],
                num_entangler_inputs,
            )
        if edge_counter_channels:
            _LOGGER.info(
                "RTIO Channels %i -> %i configured as input edge counters",
                edge_counter_channels[0],
                edge_counter_channels[-1],
            )

        # add reference PHY
        if reference_pad is not None:
            pads, eem, physical_index = reference_pad
            phy = io_class["input"](pads.p, pads.n)
            target.submodules += phy
            reference_phy = phy
            target.rtio_channels.append(rtio.Channel.from_phy(phy))
            _LOGGER.info(
                "Adding reference PHY as input on RTIO channel %i (%s)",
                len(target.rtio_channels) - 1,
                _pad_label(eem, physical_index),
            )
        else:
            reference_phy = None

        if eem_interface is not None:
            if_pads = [
                target.platform.request("if{}".format(eem_interface), i)
                for i in range(num_if_pins)
            ]
        else:
            if_pads = None

        # *** Add PHYs to Entangler gateware ***
        phy = entangler.phy.Entangler(
            core_link_pads=if_pads,
            output_pads=output_pads,
            passthrough_sigs=output_sigs,
            input_phys=input_phys,
            reference_phy=reference_phy,
            simulate=False,
        )
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))
        _LOGGER.info("Added Entangler PHY on channel %i", len(target.rtio_channels) - 1)

        unused_input_pads = list(input_pads_iter)
        if unused_input_pads:
            _LOGGER.debug(
                "Leaving %i unused input pads unallocated: %s",
                len(unused_input_pads),
                ", ".join(_pad_label(eem, i) for _, eem, i in unused_input_pads),
            )

        # Allocate any remaining output-capable pads to DIO output.
        for pad, eem, physical_index in output_pads_iter:
            phy = io_class["output"](pad.p, pad.n)
            target.submodules += phy
            target.rtio_channels.append(rtio.Channel.from_phy(phy))
            _LOGGER.debug(
                "Added spare output %s to Entangler DIO",
                _pad_label(eem, physical_index),
            )


if __name__ == "__main__":
    # run the basic kasli_generic with logging & the entangler processor.
    logging.basicConfig(level=logging.INFO)
    _add_eem_to_artiq_build(_ARTIQ_MAJOR_VERSION)
    kasligen.main()

"""Helpers for mapping Entangler DIO pads to exported standalone TTL names."""

from dataclasses import dataclass
from typing import List
from typing import Optional
from typing import Sequence

DIO_INPUT_INDICES = (0, 1, 2, 3)
DIO_OUTPUT_INDICES = (4, 5, 6, 7)


@dataclass(frozen=True)
class PhysicalTtlChannel:
    """A single physical TTL position on an Entangler DIO port."""

    port_index: int
    eem_port: int
    physical_index: int
    direction: str

    @property
    def exported_ttl_index(self) -> int:
        return (self.port_index * 8) + self.physical_index

    @property
    def exported_name(self) -> str:
        return "ttl{}".format(self.exported_ttl_index)

    @property
    def counter_name(self) -> str:
        return "{}_counter".format(self.exported_name)

    @property
    def pad_label(self) -> str:
        return "dio{}[{}]".format(self.eem_port, self.physical_index)


@dataclass(frozen=True)
class StandaloneTtlExport:
    """A standalone TTL or edge-counter device exported into the DDB."""

    physical_channel: PhysicalTtlChannel
    rtio_channel: int
    device_name: str
    device_class: str
    device_kind: str


@dataclass(frozen=True)
class EntanglerDioAllocation:
    """Physical DIO allocation for a standalone Entangler configuration."""

    inputs: Sequence[PhysicalTtlChannel]
    outputs: Sequence[PhysicalTtlChannel]
    reference_input: Optional[PhysicalTtlChannel] = None
    running_output: Optional[PhysicalTtlChannel] = None


def _build_pool(
        ports: Sequence[int], physical_indices: Sequence[int], direction: str
) -> List[PhysicalTtlChannel]:
    return [
        PhysicalTtlChannel(
            port_index=port_index,
            eem_port=eem_port,
            physical_index=physical_index,
            direction=direction,
        )
        for port_index, eem_port in enumerate(ports)
        for physical_index in physical_indices
    ]


def allocate_entangler_dio(
        ports: Sequence[int],
        num_inputs: int,
        num_outputs: int,
        num_reference_inputs: int = 0,
        num_running_outputs: int = 0,
) -> EntanglerDioAllocation:
    """Allocate Entangler DIO pads using the same physical split as gateware."""
    input_pool = _build_pool(ports, DIO_INPUT_INDICES, "input")
    output_pool = _build_pool(ports, DIO_OUTPUT_INDICES, "output")

    needed_inputs = num_inputs + num_reference_inputs
    needed_outputs = num_outputs + num_running_outputs
    if needed_inputs > len(input_pool):
        raise ValueError(
            "Requested {} Entangler input-side pads, but only {} are available".format(
                needed_inputs, len(input_pool)
            )
        )
    if needed_outputs > len(output_pool):
        raise ValueError(
            "Requested {} Entangler output-side pads, but only {} are available".format(
                needed_outputs, len(output_pool)
            )
        )

    inputs = tuple(input_pool[:num_inputs])
    reference_input = input_pool[num_inputs] if num_reference_inputs else None
    outputs = tuple(output_pool[:num_outputs])
    running_output = output_pool[num_outputs] if num_running_outputs else None
    return EntanglerDioAllocation(
        inputs=inputs,
        outputs=outputs,
        reference_input=reference_input,
        running_output=running_output,
    )


def build_standalone_ttl_exports(
        ports: Sequence[int],
        num_inputs: int,
        num_outputs: int,
        edge_counters_enabled: bool = False,
) -> Sequence[StandaloneTtlExport]:
    """Return exported TTL/counter devices for standalone Entangler DDB generation.

    Exported device names follow physical front-panel numbering while RTIO channels
    stay in the gateware append order: outputs first, then inputs, with each
    optional edge counter immediately after its input.
    """
    allocation = allocate_entangler_dio(
        ports=ports,
        num_inputs=num_inputs,
        num_outputs=num_outputs,
    )
    exports = []
    rtio_channel = 0

    for physical in allocation.outputs:
        exports.append(
            StandaloneTtlExport(
                physical_channel=physical,
                rtio_channel=rtio_channel,
                device_name=physical.exported_name,
                device_class="TTLOut",
                device_kind="output",
            )
        )
        rtio_channel += 1

    for physical in allocation.inputs:
        exports.append(
            StandaloneTtlExport(
                physical_channel=physical,
                rtio_channel=rtio_channel,
                device_name=physical.exported_name,
                device_class="TTLInOut",
                device_kind="input",
            )
        )
        rtio_channel += 1
        if edge_counters_enabled:
            exports.append(
                StandaloneTtlExport(
                    physical_channel=physical,
                    rtio_channel=rtio_channel,
                    device_name=physical.counter_name,
                    device_class="EdgeCounter",
                    device_kind="counter",
                )
            )
            rtio_channel += 1

    return tuple(exports)

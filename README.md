# Entangler

FPGA code & ARTIQ coredevice driver for generating entanglement between multiple ions.

## Functionality

An ``entangler`` works by repeating the same sequence of outputs continuously until it
receives an entanglement signature (herald) within a certain time window.
The output sequence and desired inputs can be configured at runtime with software calls.
One sequence of setting outputs and then observing inputs is called a "cycle".
Then you trigger the sequencers & pattern matchers to run successive cycles,
and it will either time out or stop when it has detected entanglement.

## Components

This repository is organized into several folders.

The ``entangler`` folder holds the gateware ([core.py](./entangler/core.py)
and [phy.py](./entangler/phy.py)) that describes how the entangler works.
It also holds the [ARTIQ](http://github.com/m-labs/artiq) coredevice driver
[driver.py](./entangler/driver.py) that sets up the entangler, triggers it,
and gets information from it.

There are also tests in a separate directory, which can be run with ``pytest -m "not slow"``.

See the [README](./entangler/README.md) for complete information.

## 2-Input / 2-Output Kasli DIO Setup

For the DIO TTL EEM wiring used in this repository, the DIO bank is treated as a
fixed split:

- ``dioX[0]`` through ``dioX[3]`` are input pads
- ``dioX[4]`` through ``dioX[7]`` are output pads

The Kasli builder now allocates entangler and generic inputs only from the lower
half of each DIO bank, and allocates entangler outputs only from the upper half.
This avoids assigning output PHYs onto detector pins.

For a simple single-card setup with two detector inputs and two entangler outputs:

- set ``NUM_ENTANGLER_INPUT_SIGNALS = 2``
- set ``NUM_OUTPUT_CHANNELS = 2``
- set ``NUM_GENERIC_INPUT_SIGNALS = 0``
- set ``"uses_reference": false`` in the Kasli JSON
- set ``"running_output": false`` in the Kasli JSON
- use a single DIO EEM in ``"ports"``

With that configuration, the expected physical mapping is:

- ``input 0 -> dioX[0]``
- ``input 1 -> dioX[1]``
- ``output 0 -> dioX[4]``
- ``output 1 -> dioX[5]``

RTIO channel numbering is still unchanged at the driver level: outputs come first,
then the input-side channels and any optional edge-counter channels, then the
entangler core channel.

The generated standalone TTL names intentionally follow physical DIO numbering
instead of RTIO append order. For a single 4-input / 4-output DIO bank, the
device DB exports ``ttl0``-``ttl3`` for the physical input-side pads and
``ttl4``-``ttl7`` for the physical output-side pads, even though the output RTIO
channels are created first internally. Optional edge counters use the same
physical input labels, e.g. ``ttl0_counter``.

## Authors

Originally designed by the Oxford Ion Trap Group (@cjbe & @dnadlinger), extended/modified
by Drew Risinger (University of Maryland, Chris Monroe Ion Trap Group) (@drewrisinger).

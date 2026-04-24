# Atom-Photon Parity Gateware Redesign

This document describes a new implementation path for the MadMax atom-photon
parity experiment. It is intentionally experiment-specific: the first target is
to remove Python from the time-critical path after a photon click and before the
microwave mapping pulse.

## Current Mismatch

The existing `EntanglerCore` repeats a fixed output cycle, gates inputs, pattern
matches at the end of the cycle, and returns a success reason to the ARTIQ kernel
through `run_mu()`. That is a good remote-entanglement primitive, but it stops at
the exact point where this experiment needs deterministic hardware behavior. In
the supplied experiment, Python receives SPCM timestamps, branches on exclusive
single-photon outcomes, and then schedules microwave/RF/blow-away/parity actions
with `at_mu()`. The branch and follow-up schedule therefore pay the blocking
`run_mu()`/kernel path cost.

The redesign keeps the legacy core intact and adds a new atom-photon parity
sequencer beside it until the new path is validated.

## Hardware Boundary

### Must Remain Host, CPU, Or External Device Control

- Waveplate motor moves such as `move_to_target_deg()`. They are millisecond to
  second scale, involve device protocols outside this gateware, and are not part
  of the photon-click critical path.
- Laser feedback and stabilizer calls. These use complex host/RPC/device logic
  and should prepare the experiment before the hardware sequencer is armed.
- Dataset appends, final analysis arrays, and measurement bookkeeping visible to
  the host. Gateware should return compact result records; the host should format
  and append datasets.
- Loading routines such as `load_until_atom_smooth_FORT_recycle()`. The decision
  loop is high level and may call many devices. Gateware can later expose an atom
  loaded result, but loading itself should stay host-side.
- DAC coil setpoint changes through Zotino in this first path. These are slow
  compared with the click-to-MW window and should be done before arming the
  critical sequencer, or represented later as coarse preloaded trigger events.
- DDS frequency/amplitude SPI retunes in the post-click critical path. A gateware
  TTL/profile-select trigger can be deterministic; a full DDS SPI transaction is
  not a minimal low-latency feature of this repo. The near-term design therefore
  represents DDS retunes as programmable output action bits that trigger
  preloaded profiles, RTIO-DMA, or external profile-select wiring.

### Should Move Into Gateware

- Excitation attempt timing: FORT off/on window, excitation/GRIN pulse, photon
  collection gate, and repeated attempts.
- First-click timestamp capture for SPCM0 and SPCM1 with fine input timestamps.
- Exclusive branch decision with explicit outcomes:
  `SPCM0-only`, `SPCM1-only`, `both`, and `neither`.
- Retry/stop policy for `both` and `neither`.
- Timestamp-relative action sequencing after an exclusive click:
  microwave switch pulse, optional RF pulse enable, DDS/profile trigger bits,
  FORT restore trigger, blow-away trigger, and parity-readout trigger.
- Compact result reporting: final outcome, chosen timestamp, individual SPCM
  timestamps, number of attempts completed, and done/failure reason.
- The atom-check and recooling control surface. Full atom-retention loops need
  edge counters and slower cooling/DAC orchestration, so the first implementation
  stubs these controls while reserving the API and result fields.

## Proposed Architecture

This should be a new experiment-specific core with a small microcoded action
sequencer, not a generic branch-on-event RTIO engine. A generic engine would add
policy and validation complexity before solving the actual bottleneck. The right
shape is:

- `Attempt sequencer`: owns the attempt clock, FORT/excitation windows, photon
  gate offsets, and up to `n_excitation_attempts` retries.
- `Photon event detector`: gates SPCM0/SPCM1, records first timestamps, and
  computes the four explicit outcomes.
- `Branch decision engine`: accepts exactly one detector as success; applies
  configurable retry/stop policy to both/neither.
- `Timestamp-relative action sequencer`: starts from the chosen photon timestamp
  and plays a branch-specific action table. Each entry has `offset_mu`,
  `duration_mu`, `output_mask`, and `output_value`.
- `Loop controller`: first pass handles repeated excitation attempts and done
  signaling. Future passes add atom-check count windows, retention thresholding,
  recooling action blocks, and measurement loop termination.
- `Programmable parameter memory`: host loads timings, policies, action tables,
  and stub atom-check/recooling parameters. Experiment constants are not hard
  coded into RTL.
- `Status/result reporting`: exposes outcome, timestamps, attempts completed,
  success/failure, and reason codes.

## Timing Model

Input timestamps use the existing TTL SERDES style: 8 ns coarse clock with a
3-bit fine timestamp, so detector timestamps are represented in machine units.
Output actions are driven on the coarse RTIO/gateware clock. The action table is
specified in machine units, but output edges are emitted on the next represented
coarse edge. This matches the existing entangler limitation that outputs are
coarse-timed while input timestamps retain fine timing.

Exclusive branching cannot be known until the photon collection window closes,
unless the design speculatively starts a mapping pulse and later cancels it. This
first implementation does not do speculative actions. Therefore
`t_start_MW_mapping_mu` must be large enough to cover the worst-case time from
click timestamp to gate close plus branch/action FSM latency. The host validator
rejects action offsets below the photon gate width plus a conservative branch
latency margin. This is the honest
minimum feature set that still beats the current Python `run_mu()` path:

- capture both first-click timestamps in hardware,
- decide exclusive branch immediately after the photon gate closes,
- schedule MW/RF/TTL actions from the chosen timestamp without returning to
  Python.

## DDS, TTL, RF, And FORT Representation

Timing registers in the new path should carry one full 32-bit machine-unit value
per write. This deliberately avoids the old core's compact 16-bit start/stop
packing, which is convenient for short cycles but too cramped for the longer
atom-retention and recooling loop that this experiment will grow into.

The atom-photon PHY maps the first two physical outputs to attempt-level timing
signals, then uses the remaining action bits for post-click branch actions:

| Bit | Meaning |
| --- | --- |
| 0 | FORT gate/off control during each attempt |
| 1 | excitation/GRIN gate during each attempt |
| 2 | microwave switch pulse |
| 3 | MW/RF switch or RF DDS switch |
| 4 | DDS/profile retune trigger |
| 5 | blow-away trigger |
| 6 | parity readout trigger |
| 7 | atom-check or recooling trigger |

The host decides the polarity and wiring. For example, if the lab TTL
microwave switch is active-low, the output bit can drive a small polarity layer
or external inversion rather than baking lab polarity into the core.

## Atom Check And Recooling

The first prototype reserves atom-check and recooling configuration, but it does
not yet implement the full atom-retention loop. The realistic hardware path is:

- gate SPCM edge counters during atom check,
- compare `(SPCM0 + SPCM1) / 2` or a configured count sum against a threshold,
- branch to retry/finish based on atom retained,
- optionally play a coarse recooling action block before the next excitation
  cycle.

Cooling light and coil setpoint changes that require DDS SPI or Zotino writes
remain host-prepared or externally triggered in the first implementation.

## Host API Sketch

The host should configure the sequencer with an experiment-shaped object:

```python
config = AtomPhotonParityConfig(
    n_excitation_attempts=100,
    attempt_period_mu=2000,
    fort_off_mu=0,
    fort_on_mu=collection_time_mu + 50,
    excitation_start_mu=t_excitation_offset_mu,
    excitation_stop_mu=t_excitation_offset_mu + t_excitation_pulse_mu,
    photon_gate_start_mu=gate_start_offset_mu,
    photon_gate_stop_mu=gate_start_offset_mu + collection_time_mu,
    branch0_actions=[...],
    branch1_actions=[...],
)
```

Driver responsibilities:

- validate impossible windows and too-early post-click actions,
- write timing registers and branch action tables,
- start the sequencer,
- read compact result/status words,
- leave dataset appends and high-level experiment flow to host Python.

## Tests And Simulations

The first simulation suite should prove:

- SPCM0-only click chooses branch 0 and plays branch 0 actions.
- SPCM1-only click chooses branch 1 and plays branch 1 actions.
- Both-click and neither-click outcomes are explicit and configurable.
- MW/action timing is relative to the captured photon timestamp.
- Retry works across multiple excitation attempts.
- Done signaling occurs after action playback or terminal failure.
- Host configuration packs the expected register writes.
- Invalid gate windows and unsafe action offsets are rejected.

Later simulations should add atom-check counter thresholds, recooling branches,
and an integrated RTIO PHY/register test once the critical-path core is stable.

## Migration Path

1. Keep `EntanglerCore`, `phy.py`, and the existing driver unchanged.
2. Add `atom_photon_core.py`, `atom_photon_driver.py`, and
   `atom_photon_registers.py` as an isolated implementation path.
3. Validate the critical path in Migen simulation.
4. Add an RTIO PHY wrapper for the new core and a Kasli JSON option such as
   `"mode": "atom_photon_parity"` once the register map is stable.
5. Port the experiment one block at a time: first replace the Python
   post-click MW mapping, then add blow-away/parity triggers, then atom-check
   and recooling loops.

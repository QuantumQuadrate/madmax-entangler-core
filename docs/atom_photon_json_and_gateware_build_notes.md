# Atom-Photon JSON Description And Gateware Build Notes

This note describes the Kasli JSON description for the current repository state
and what to watch before building gateware for the atom-photon parity redesign.

## Current Kasli Integration

On this redesign branch, the Kasli JSON builder treats:

```json
{ "type": "entangler", ... }
```

as the atom-photon parity entangler. The legacy `entangler.phy.Entangler` still
exists in the repo, but `entangler/kasli_generic.py` now instantiates
`entangler.atom_photon_phy.AtomPhotonParity`.

The optional `"mode": "atom_photon_parity"` field is accepted for clarity. Other
modes are rejected.

## Recommended Buildable JSON Today

For the atom-photon hardware layout, start with a standalone entangler on two DIO
EEM ports:

```json
{
  "target": "kasli",
  "variant": "madmax_atom_photon_parity",
  "hw_rev": "v1.1",
  "base": "standalone",
  "core_addr": "192.168.78.185",
  "rtio_frequency": 125e6,
  "peripherals": [
    {
      "type": "entangler",
      "mode": "atom_photon_parity",
      "ports": [0, 1],
      "uses_reference": false,
      "running_output": false,
      "edge_counter": true
    }
  ]
}
```

Adjust `ports`, `hw_rev`, and `core_addr` for the actual Kasli crate.

### Why Two DIO Ports?

The builder treats each DIO EEM as a fixed split:

- `dioX[0:4]` are input-side pads,
- `dioX[4:8]` are output-side pads.

One DIO port gives only four output-side pads. The atom-photon parity sequencer
is expected to want up to eight deterministic action bits:

| Output bit | Suggested use |
| --- | --- |
| 0 | FORT gate/off control |
| 1 | excitation/GRIN gate |
| 2 | microwave switch |
| 3 | RF/MW-RF switch |
| 4 | DDS/profile retune trigger |
| 5 | blow-away trigger |
| 6 | parity readout trigger |
| 7 | atom-check or recooling trigger |

Using two DIO ports gives eight output-side pads. With the default settings in
`entangler/settings.toml`, it also gives enough input-side pads for four
entangler inputs plus four generic inputs.

## Settings To Check Before Building

The JSON file does not set the number of entangler inputs or outputs. Those come
from `entangler/settings.toml` or Dynaconf environment overrides.

Current default:

```toml
NUM_OUTPUT_CHANNELS = 8
NUM_ENTANGLER_INPUT_SIGNALS = 4
NUM_GENERIC_INPUT_SIGNALS = 4
NUM_PATTERNS_ALLOWED = 4
```

For the first atom-photon parity prototype, the minimum conceptual I/O is:

```toml
NUM_OUTPUT_CHANNELS = 8
NUM_ENTANGLER_INPUT_SIGNALS = 2
NUM_GENERIC_INPUT_SIGNALS = 0
```

Changing these settings affects the atom-photon PHY register width assumptions
and physical DIO allocation. For the current branch, keep at least two entangler
inputs and eight outputs.

## Physical Mapping With `ports: [0, 1]`

With the default DIO split:

- `SPCM0` should be on `dio0[0]`.
- `SPCM1` should be on `dio0[1]`.
- Additional detector/generic input pads, if enabled, continue on `dio0[2]`,
  `dio0[3]`, then `dio1[0:4]`.
- Output action bits map first to `dio0[4:8]`, then `dio1[4:8]`.

For the atom-photon parity core, the output mapping is:

- output bit 0 -> `dio0[4]`,
- output bit 1 -> `dio0[5]`,
- output bit 2 -> `dio0[6]`,
- output bit 3 -> `dio0[7]`,
- output bit 4 -> `dio1[4]`,
- output bit 5 -> `dio1[5]`,
- output bit 6 -> `dio1[6]`,
- output bit 7 -> `dio1[7]`.

Confirm the polarity of each lab TTL path. For example, the experiment code uses
`ttl_microwave_switch.off()` to apply the microwave pulse. The new action table
only drives bits; polarity should be handled by a small polarity layer, external
inversion, or explicit action values.

## Optional JSON Fields

`uses_reference` should be `false` for this atom-photon parity application unless
you intentionally want Oxford-style reference-triggered gates. The supplied
experiment gates relative to an attempt timeline, not an external reference
pulse.

`running_output` reserves one extra output-side pad for a hardware running
indicator. Leave it `false` if you need all eight action outputs.

`edge_counter` may be useful in the transition period because it adds ARTIQ edge
counters for allocated input pads. That can support host-side atom checks while
the first atom-check loop is still outside the new core. It does not by itself
move atom-check thresholding into the atom-photon core.

`link_eem` and `uses_reference` are rejected in atom-photon parity mode. The
sequencer gates relative to its own attempt timeline rather than an external
reference pulse or a second Kasli.

## Gateware Build Checklist

Before building:

1. Confirm `entangler/settings.toml` has enough output channels for every action
   bit you intend to wire.
2. Confirm the JSON `ports` list has enough DIO EEMs for the requested input and
   output counts.
3. Keep `uses_reference: false` for this experiment path.
4. Avoid `running_output: true` unless you intentionally give up one output pad.
5. If using `edge_counter: true`, confirm your ARTIQ version supports the edge
   counter PHY used by `entangler/kasli_generic.py`.
6. Build from the same Python/ARTIQ environment that provides `migen`, `artiq`,
   `numpy`, `dynaconf`, and `mergedeep`.
7. Run the simulation tests in that environment before flashing gateware.
8. Check the generated build log and device DB channel numbers. RTIO channels are
   not the same as physical DIO labels.

Example build command:

```bash
python -m entangler.kasli_generic path/to/atom_photon_parity.json
```

For a fast structural check without a full compile, use the ARTIQ builder flags
available in your environment, for example:

```bash
python -m entangler.kasli_generic path/to/atom_photon_parity.json \
  --no-compile-software --no-compile-gateware
```

## What Still Needs Implementation Before Experimental Use

The atom-photon parity sequencer is now connected to the Kasli builder. Before
using it in the experiment, the repo still needs:

- broader hardware simulation in the real ARTIQ/Migen environment,
- full atom-check threshold/recooling implementation rather than the current
  reserved interface,
- polarity confirmation for each lab TTL path.

The current gateware path covers the critical click-to-branch action loop first.

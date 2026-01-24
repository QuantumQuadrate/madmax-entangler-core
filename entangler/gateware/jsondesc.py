import json
import pathlib

import mergedeep

import artiq.coredevice.jsondesc

import entangler

__all__ = ['inject']

_PERIPHERAL_NAMES_KEY = 'definitions.peripheral.properties.type.enum'.split('.')
"""Key to the list of peripheral names in the JSON schema."""


def _rget(o, key):
    if key:
        return _rget(o[key[0]], key[1:])
    else:
        return o


def inject():
    """Inject custom peripherals into the ARTIQ JSON validator."""

    # Find JSON files of peripherals
    json_files = list(pathlib.Path(__file__).parent.joinpath('peripheral_schemas').rglob('*.json'))

    # Add specific JSON files from external libraries
    json_files.extend([
        pathlib.Path(entangler.__file__).parent / "entangler_eem.schema.json",
    ])

    if json_files:
        for peripheral_json in json_files:
            # Get existing peripheral names
            existing_names = set(_rget(artiq.coredevice.jsondesc.schema, _PERIPHERAL_NAMES_KEY))

            # Read JSON file
            with open(peripheral_json) as f:
                peripheral = json.load(f)

            # Get new peripheral names
            peripheral_names = set(_rget(peripheral, _PERIPHERAL_NAMES_KEY))

            if not existing_names & peripheral_names:
                # Merge schemas
                mergedeep.merge(
                    artiq.coredevice.jsondesc.schema,
                    peripheral,
                    strategy=mergedeep.Strategy.TYPESAFE_ADDITIVE,
                )
            else:
                raise ValueError('Could not merge schema, peripheral already exists: {}'.format(peripheral_json))

        # Update validator
        artiq.coredevice.jsondesc.validator = artiq.coredevice.jsondesc.extend_with_default(
            artiq.coredevice.jsondesc.Draft7Validator)(artiq.coredevice.jsondesc.schema)

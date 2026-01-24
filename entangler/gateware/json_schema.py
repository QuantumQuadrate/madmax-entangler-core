#!/usr/bin/env python3

"""Frontend for the ARTIQ JSON schema validator for Kasli system description files."""

import argparse

import artiq.coredevice.jsondesc

import gateware.jsondesc


def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='JSON schema validator for Kasli system description files')
    parser.add_argument('files', type=str, nargs='+', help='JSON system description files')
    args = parser.parse_args()

    # Inject custom peripherals in JSON schema
    gateware.jsondesc.inject()

    for f in args.files:
        # Validate JSON file
        print('Validating file "{}"...'.format(f))
        artiq.coredevice.jsondesc.load(f)
        print('JSON system description is valid')


if __name__ == "__main__":
    main()

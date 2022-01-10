# Nix Scripts

## Assumptions

This assumes that you have already added the main ARTIQ Nix channel (``<artiq-full>``, see [ARTIQ Manual](https://m-labs.hk/artiq/manual/installing.html#installing-via-nix-linux)).

## Entangler package

To build gateware, the entangler package requires:
* ARTIQ5: commit 52112d54f9c052159b88b78dc6bd712abd4f062c or https://github.com/m-labs/artiq/pull/1426 must be incorporated. If you are using the latest version of ARTIQ 5 after Feb 2020, this should be fine.
* ARTIQ6: any version. Hardware functionality hasn't been fully tested.
* ARTIQ7: any version. Hardware functionality hasn't been fully tested.
seen in artiq/gateware/targets/kasli_generic.py.

If you just want to use the entangler package, simply use/modify the following snippet to add it to your environment:
```nix
{ pkgs ? import <nixpkgs> { }
, buildGateware ? true
}:
let
  entanglerSrc = fetchFromGitHub {
    owner = "drewrisinger";
    repo = "entangler-core";
    rev = "{insert commit/tag here}";
    sha256 = lib.fakeSha256; # try building with this once, then replace it with the SHA that the error message gives you
  };
  entanglerPackage = pkgs.callPackage "${entanglerSrc}/nix" { inherit buildGateware; };
in
  pkgs.mkShell {
    buildInputs = [
      (pkgs.python3.withPackages(ps: [ entanglerPackage ]))
    ];
  }
```

## Building Entangler Gateware

To launch a shell where you can build Entangler Gateware, you need a Xilinx license and a local ARTIQ repo clone. You can then build the
Entangler gateware with

```bash
nix-shell /ENTANGLER/PATH/nix/entangler-shell-dev.nix --run "python -m entangler.kasli_generic /PATH/TO/KASLI_DESCRIPTOR.json"
```

This can then be flashed with:
```bash
# following lines from ARTIQ manual
artiq_mkfs flashstorage_with_mac_and_ip.img -s ip IP.ADDRESS.X.Y -s mac FU:LL:MA:C0:AD:DR
artiq_flash -t kasli -V KASLI_DESCRIPTOR_NAME -d ./artiq_kasli/ --srcbuild -f flashstorage_with_mac_and_ip.img
```

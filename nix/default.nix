{ pkgs ? import <nixpkgs> { }
, artiqpkgs ? import <artiq-full> { }
, buildGateware ? true  # whether the requirements for building gateware should be added. Setting to false reduces requirements, but is useful if you just want to use the coredevice drivers in experiments.
}:

# To run this package in development mode (where code changes are reflected in shell w/o restart),
# run this Nix shell by itself. It lacks some of the packages needed to build a full ARTIQ
# bootloader/gateware file, but it's good for testing internal stuff.
# i.e. ``nix-shell ./default.nix``

let
  entangler-deps = pkgs.callPackage ./entangler-dependencies.nix { };
in
pkgs.python3Packages.callPackage ./derivation.nix {
  inherit (artiqpkgs) artiq migen misoc;
  inherit (entangler-deps) dynaconf;
  inherit buildGateware;
}

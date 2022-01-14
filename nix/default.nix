{ pkgs ? import <nixpkgs> {}
, artiqpkgs ? import <artiq-full> {}
, buildGateware ? true  # whether the requirements for building gateware should be added. Setting to false reduces requirements, but is useful if you just want to use the coredevice drivers in experiments.
}:

# To run this package in development mode (where code changes are reflected in shell w/o restart),
# run this Nix shell by itself. It lacks some of the packages needed to build a full ARTIQ
# bootloader/gateware file, but it's good for testing internal stuff.
# i.e. ``nix-shell ./default.nix``


let
  entangler-src = ./..;
  entangler-deps = pkgs.callPackage ./entangler-dependencies.nix {};
  lib = pkgs.lib;
  python3Packages = pkgs.python3Packages;
in
  python3Packages.buildPythonPackage rec {
    pname = "entangler";
    version = "1.2.0.post0";

    src = lib.cleanSource entangler-src;

    buildInputs = with python3Packages; [ pytestrunner ];

    propagatedBuildInputs = [
      artiqpkgs.artiq
      entangler-deps.dynaconf
    ] ++ lib.optionals buildGateware [
      python3Packages.jsonschema # really a dependency of artiq.coredevice.jsondesc, but that's imported by entangler.kasli_generic so it's functionally a requirement
      python3Packages.mergedeep
      artiqpkgs.migen
      artiqpkgs.misoc
    ];

    doCheck = buildGateware;  # all pytest tests are actually gateware tests, require migen
    checkInputs = [ python3Packages.pytestCheckHook ];
    pytestFlagsArray = [
      "-m 'not slow'"
    ];
    pythonImportsCheck = [ pname "${pname}.driver" ]
      ++ lib.optionals buildGateware [ "${pname}.kasli_generic" "${pname}.core" "${pname}.phy" ];

    meta = with lib; {
      description = "ARTIQ extension to generate & check patterns (for entanglement).";
      homepage = "https://github.com/drewrisinger/entangler-core/";
      license = licenses.gpl3;
      platforms = platforms.all;
      maintainers = with maintainers; [ drewrisinger ];
    };
  }

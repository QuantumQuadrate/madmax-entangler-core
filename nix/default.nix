{ pkgs ? import <nixpkgs> {}
, artiqpkgs ? import <artiq-full> {}
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
    version = "1.1.1";

    src = lib.cleanSource entangler-src;

    buildInputs = with python3Packages; [ pytestrunner ];

    propagatedBuildInputs = [
      artiqpkgs.artiq
      entangler-deps.dynaconf
      artiqpkgs.migen
      artiqpkgs.misoc
    ];

    doCheck = true;
    checkInputs = [ python3Packages.pytestCheckHook ];
    pytestFlagsArray = [
      "-m 'not slow'"
    ];
    pythonImportsCheck = [ pname "${pname}.kasli_generic" "${pname}.driver" "${pname}.phy" ];

    meta = with lib; {
      description = "ARTIQ extension to generate & check patterns (for entanglement).";
      homepage = "https://github.com/drewrisinger/entangler-core/";
      license = licenses.gpl3;
      platforms = platforms.all;
      maintainers = with maintainers; [ drewrisinger ];
    };
  }

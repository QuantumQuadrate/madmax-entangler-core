{
  description = "Entangler Core (ARTIQ extension)";

  inputs = {
    # Keep entangler aligned with ARTIQ's nixpkgs by default.
    artiqpkgs.url = "git+https://github.com/QuantumQuadrate/madmax-artiq.git";
    nixpkgs.follows = "artiqpkgs/nixpkgs";

    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, artiqpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        ap = artiqpkgs.packages.${system};

        # --- Critical bit: make entangler use the SAME python package set as ARTIQ if exposed ---
        #
        # Depending on how the ARTIQ flake is structured, ap may or may not expose python3Packages.
        # When it does, using that avoids the Python 3.12 vs 3.13 mismatch you hit.
        pythonPkgs =
          if ap ? python3Packages then ap.python3Packages
          else pkgs.python3Packages;

        python = pythonPkgs.python;

        entangler-deps = pkgs.callPackage ./entangler-dependencies.nix {
          python3Packages = pythonPkgs;
        };

        mkEntangler = buildGateware:
          pythonPkgs.callPackage ./derivation.nix {
            inherit (pkgs) lib;

            # Pull ARTIQ + (optional) gateware deps from the ARTIQ package set.
            inherit (ap) artiq;
            migen = ap.migen or null;
            misoc = ap.misoc or null;

            inherit (entangler-deps) dynaconf;

            inherit buildGateware;

            # Gateware-only python deps
            jsonschema = pythonPkgs.jsonschema;
            mergedeep = pythonPkgs.mergedeep;

            # Tests
            pytestCheckHook = pythonPkgs.pytestCheckHook;

            # Unused in your derivation but sometimes needed by buildPythonPackage callers:
            pytestrunner = pythonPkgs.pytestrunner or null;
            numpy = pythonPkgs.numpy;
          };

        entangler = mkEntangler true;
        entangler-no-gateware = mkEntangler false;

        # A python interpreter that can `import entangler`
        pythonWithEntangler = python.withPackages (_ps: [
          entangler
        ]);

        pythonWithEntanglerNoGateware = python.withPackages (_ps: [
          entangler-no-gateware
        ]);
      in
      {
        packages = {
          inherit entangler entangler-no-gateware;
          default = entangler;
        };

        devShells = {
          # Fast “python import entangler” shell (no Vivado requirement)
          default = pkgs.mkShell {
            name = "entangler-core-dev-shell";
            buildInputs = [
              pythonWithEntanglerNoGateware
            ];
          };

          # Gateware-capable shell (pulls in extra deps; Vivado is still your system install)
          gateware = pkgs.mkShell {
            name = "entangler-core-gateware-shell";
            buildInputs = [
              pythonWithEntangler
            ];
            shellHook = ''
              # If you have Vivado installed system-wide, this makes it available automatically.
              if [ -f /opt/Xilinx/Vivado/2022.2/settings64.sh ]; then
                source /opt/Xilinx/Vivado/2022.2/settings64.sh
              fi
            '';
          };
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    );

  nixConfig = {
    extra-trusted-public-keys = [
      "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc="
    ];
    extra-substituters = [
      "https://nixbld.m-labs.hk"
    ];

    # If you rely on Vivado living in /opt inside sandboxed builds/shells
    extra-sandbox-paths = [
      "/opt"
    ];
  };
}

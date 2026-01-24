{
  description = "Entangler Core (ARTIQ extension) - single-file modern flake";

  inputs = {
    # Use the same nixpkgs as ARTIQ to stay consistent with its Python/toolchain
    artiqpkgs.url = "git+https://github.com/QuantumQuadrate/madmax-artiq.git";
    nixpkgs.follows = "artiqpkgs/nixpkgs";

    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, artiqpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        ap = artiqpkgs.packages.${system};

        # Prefer ARTIQ's Python package set if exposed (prevents 3.12 vs 3.13 mismatches)
        pythonPkgs =
          if ap ? python3Packages then ap.python3Packages
          else pkgs.python3Packages;

        python = pythonPkgs.python;

        # -------------------------
        # dynaconf (inline)
        # -------------------------
        dynaconf = pythonPkgs.buildPythonPackage rec {
          pname = "dynaconf";
          version = "3.2.6";

          src = pythonPkgs.fetchPypi {
            inherit pname version;
            # From your snippet; modern nix uses `hash` (sha256 works too on many nixpkgs)
            hash = "sha256-dMwYlzljgLuVdzDrNBzAl27pw4u8tTPTMHxQyu0K3vk=";
          };

          # Works on current nixpkgs Python builders
          pyproject = true;
          build-system = [ pythonPkgs.setuptools ];

          propagatedBuildInputs = with pythonPkgs; [
            click
            python-box
            python-dotenv
            toml
          ];

          doCheck = false;

          meta = with pkgs.lib; {
            homepage = "https://github.com/rochacbruno/dynaconf";
            description = "The dynamic configurator for your Python Project";
            license = licenses.mit;
          };
        };

        # -------------------------
        # entangler (inline)
        # -------------------------
        #
        # This repo layout (per your output) has:
        #   ./entangler/__init__.py
        #   ./entangler/core.py
        #   ...
        #
        # So we "install" by copying the `entangler/` directory into site-packages.
        #
        mkEntangler = { buildGateware ? false }:
          pythonPkgs.buildPythonPackage rec {
            pname = "entangler";
            version = self.sourceInfo.rev or "unstable";

            src = self;

            # There may be no setup.py/pyproject; we do a manual install.
            format = "other";

            dontBuild = true;
            doCheck = false;

            # Runtime deps that entangler actually imports
            propagatedBuildInputs =
              [
                dynaconf
              ]
              # Gateware functionality dependencies (only when requested)
              ++ pkgs.lib.optionals buildGateware (with pythonPkgs; [
                jsonschema
                mergedeep
                numpy
              ] ++ (with ap; [
                # These come from ARTIQ pkgs, keep them aligned with ARTIQ
                migen
                misoc
                artiq
              ]));

            installPhase = ''
              runHook preInstall
              mkdir -p "$out/${python.sitePackages}"
              cp -r entangler "$out/${python.sitePackages}/"
              runHook postInstall
            '';

            pythonImportsCheck = [ "entangler" ];
          };

        entangler = mkEntangler { buildGateware = true; };
        entangler-no-gateware = mkEntangler { buildGateware = false; };

        pythonWithEntanglerNoGateware =
          python.withPackages (_ps: [ entangler-no-gateware ]);

        pythonWithEntanglerGateware =
          python.withPackages (_ps: [ entangler ]);
      in
      {
        packages = {
          inherit dynaconf entangler entangler-no-gateware;
          default = entangler;
        };

        devShells = {
          # Fast “import entangler” shell (no Vivado/gateware deps)
          default = pkgs.mkShell {
            name = "entangler-core-dev-shell";
            buildInputs = [
              pythonWithEntanglerNoGateware
            ];
          };

          # Gateware-capable shell (adds deps + auto-sources Vivado if you have it installed)
          gateware = pkgs.mkShell {
            name = "entangler-core-gateware-shell";
            buildInputs = [
              pythonWithEntanglerGateware
            ];

            shellHook = ''
              if [ -f /opt/Xilinx/Vivado/2022.2/settings64.sh ]; then
                # shellcheck disable=SC1091
                source /opt/Xilinx/Vivado/2022.2/settings64.sh
              else
                echo "NOTE: Vivado 2022.2 not found at /opt/Xilinx/Vivado/2022.2/settings64.sh"
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

    # If you rely on Vivado living in /opt inside sandboxed shells/builds
    extra-sandbox-paths = [
      "/opt"
    ];
  };
}

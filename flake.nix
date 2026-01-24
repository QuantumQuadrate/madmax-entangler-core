{
  description = "Entangler Core (ARTIQ extension) - single-file modern flake";

  inputs = {
    artiqpkgs.url = "git+https://github.com/QuantumQuadrate/madmax-artiq.git";
    nixpkgs.follows = "artiqpkgs/nixpkgs";

    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, artiqpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        ap = artiqpkgs.packages.${system};

        # Prefer ARTIQ's python set when available (avoids python version mismatches)
        pythonPkgs =
          if ap ? python3Packages then ap.python3Packages else pkgs.python3Packages;

        python = pythonPkgs.python;

        # -------------------------
        # dynaconf (inline)
        # -------------------------
        dynaconf = pythonPkgs.buildPythonPackage rec {
          pname = "dynaconf";
          version = "3.2.6";

          src = pythonPkgs.fetchPypi {
            inherit pname version;
            # Correct hash from your log ("got:")
            hash = "sha256-dMwYlzljgLuVdzDrNBzAl27pw4u8tT0zB8UMrtCu37g=";
          };

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
        mkEntangler = { buildGateware ? false }:
          pythonPkgs.buildPythonPackage rec {
            pname = "entangler";
            version = self.sourceInfo.rev or "unstable";
            src = self;

            # This repo doesn't necessarily have setup.py/pyproject; we install by copying.
            format = "other";
            dontBuild = true;
            doCheck = false;

            # Fix: entangler is NOT a Qt application; disable Qt wrapping if Qt sneaks in.
            dontWrapQtApps = true;

            propagatedBuildInputs =
              [
                dynaconf
              ]
              ++ pkgs.lib.optionals buildGateware (
                (with pythonPkgs; [
                  jsonschema
                  mergedeep
                  numpy
                ])
                ++ (with ap; [
                  migen
                  misoc
                  artiq
                ])
              );

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
        # DEFAULT: gateware-capable shell
        default = pkgs.mkShell {
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

        # Optional: lightweight shell (no Vivado, faster startup)
        lite = pkgs.mkShell {
            name = "entangler-core-lite-shell";
            buildInputs = [
            pythonWithEntanglerNoGateware
            ];
        };
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    );

  # These are nice-to-have but will be ignored if you aren't a trusted user.
  nixConfig = {
    extra-trusted-public-keys = [
      "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc="
    ];
    extra-substituters = [
      "https://nixbld.m-labs.hk"
    ];
    extra-sandbox-paths = [
      "/opt"
    ];
  };
}

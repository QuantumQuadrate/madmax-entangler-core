{
  description = "Entangler Core (ARTIQ gateware + Python support)";

  inputs = {
    # Use ARTIQ's nixpkgs to stay compatible with its Python/toolchain choices
    artiqpkgs.url = "git+https://github.com/m-labs/artiq?ref=release-8";

    # Keep nixpkgs aligned with ARTIQ
    nixpkgs.follows = "artiqpkgs/nixpkgs";

    # Modern multi-system output helper
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, artiqpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        # ARTIQ package set for the same system
        ap = artiqpkgs.packages.${system};

        # ---- Build entangler from this repo's existing Nix entrypoint ----
        #
        # This assumes your entangler-core repo has a Nix entrypoint like:
        #   ./default.nix   OR   ./nix/default.nix
        #
        # In the upstream tag v1.4.1, consumers typically use "?dir=nix",
        # so most forks have `nix/default.nix`. Adjust `entanglerDefault`
        # below if your file lives elsewhere.
        entanglerDefault =
          if builtins.pathExists ./nix/default.nix then ./nix/default.nix
          else if builtins.pathExists ./default.nix then ./default.nix
          else throw "Could not find ./nix/default.nix or ./default.nix in entangler-core repo.";

        # Build the Python package. If your `default.nix` supports `buildGateware`,
        # you can toggle it here. Most people want it on for full functionality.
        entangler = pkgs.python3Packages.callPackage entanglerDefault {
          buildGateware = true;
          # If your default.nix wants ARTIQ deps explicitly, uncomment:
          # inherit (ap) artiq migen misoc;
        };

        # ---- Optional: a Vivado wrapper shell env (keeps your system clean) ----
        #
        # This matches the “FHS Vivado” idea you showed. It assumes Vivado
        # is installed at /opt/Xilinx/Vivado/<version>.
        vivadoVersion = "2022.2";
        filterfunc = drv:
          !((pkgs.lib.strings.hasPrefix "python3" drv.name)
            || drv.name == "vivado"
            || drv.name == "vivado-env");

        vivadoDeps = pkgs': with pkgs'; let
          # Fix ncurses5 libtinfo soname issues (common for Vivado)
          ncurses' = ncurses5.overrideAttrs (old: {
            configureFlags = (old.configureFlags or []) ++ [ "--with-termlib" ];
            postFixup = "";
          });
        in [
          libxcrypt-legacy
          (ncurses'.override { unicodeSupport = false; })
          zlib
          libuuid
          xorg.libSM
          xorg.libICE
          xorg.libXrender
          xorg.libX11
          xorg.libXext
          xorg.libXtst
          xorg.libXi
          freetype
          fontconfig
        ];

        vivado = pkgs.buildFHSUserEnv {
          name = "vivado";
          targetPkgs = vivadoDeps;
          profile = "set -e; source /opt/Xilinx/Vivado/${vivadoVersion}/settings64.sh";
          runScript = "vivado";
        };

        pythonWithEntangler = pkgs.python3.withPackages (ps: [
          entangler
          # handy sanity-check tools (optional)
          ps.packaging
          ps.jsonschema
        ]);
      in
      rec {
        packages = {
          entangler = entangler;
          default = pythonWithEntangler;
        };

        devShells = {
          # Simple “python import entangler” shell
          default = pkgs.mkShell {
            name = "entangler-core-dev-shell";
            buildInputs = [
              pythonWithEntangler
            ];
          };

          # If you want a Vivado-enabled dev shell (for gateware work)
          vivado = ap.devShells.${system}.boards.overrideAttrs (oa: {
            buildInputs =
              (builtins.filter filterfunc oa.buildInputs)
              ++ [
                pythonWithEntangler
                vivado
              ];
          });
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    );

  nixConfig = {
    # If you rely on M-Labs cache, keep these (optional)
    extra-trusted-public-keys = [
      "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc="
    ];
    extra-substituters = [ "https://nixbld.m-labs.hk" ];

    # If Vivado is installed in /opt and you want Nix builds/shells to see it
    extra-sandbox-paths = "/opt";
  };
}

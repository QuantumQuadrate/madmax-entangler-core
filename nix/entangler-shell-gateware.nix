{ pkgs ? import <nixpkgs> {}
, artiqpkgs ? import <artiq-full> {}
}:

# Use this shell to build the Gateware for the Entangler.
# Adds the Entangler package to ARTIQ's default "shell-dev.nix" environment

let
  entangler = pkgs.callPackage ./default.nix { inherit artiqpkgs; };
  mlabs-nix-scripts = builtins.fetchTarball {
    # See PR: https://git.m-labs.hk/M-Labs/nix-scripts/pulls/76
    # TODO: Revert to mainline mlabs-nix-scripts once the above PR is merged
    name = "mlabs-nix-scripts-overrideable-shell-dev.tar.gz";
    url = "https://git.m-labs.hk/drewrisinger/nix-scripts/archive/47960f539b85b05797c9596e56eda59ea148a3f7.tar.gz";
    sha256 = "0iic5fl3162zl624ks3493jv8hfdwyx6jb8llzw4ddvz1h4h2fr1";
  };
  # Force shell to use Release (i.e. MLabs Nix Channel) ARTIQ build, instead of passing all source/arguments ourselves.
  dev-artiq-shell = import "${mlabs-nix-scripts}/artiq-fast/shell-dev.nix" { inherit artiqpkgs; };
in
  pkgs.mkShell{
    # Add Entangler to the development shell
    buildInputs = [ entangler ] ++ dev-artiq-shell.buildInputs;
    inherit (dev-artiq-shell) TARGET_AR;  # Set LLVM target
  }

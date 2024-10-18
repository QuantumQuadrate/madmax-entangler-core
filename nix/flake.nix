{
  inputs = {
    artiqpkgs.url = git+https://github.com/m-labs/artiq?ref=release-8;
    nixpkgs.follows = "artiqpkgs/nixpkgs";
  };

  outputs = { self, artiqpkgs, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      entangler-deps = pkgs.callPackage ./entangler-dependencies.nix { };
      entangler-pkg = buildGateware: pkgs.python3Packages.callPackage ./derivation.nix {
        inherit (artiqpkgs.packages.x86_64-linux) artiq migen misoc;
        inherit (entangler-deps) dynaconf;
        inherit buildGateware;
      };
      entangler = entangler-pkg true;
      entangler-no-gateware = entangler-pkg false;
    in
    {
      packages.x86_64-linux = {
        inherit entangler entangler-no-gateware;
        default = entangler;
      };

      devShells.x86_64-linux.default = pkgs.mkShell {
        buildInputs = [
          (pkgs.python3.withPackages (ps: entangler.propagatedBuildInputs))
        ];
      };

      formatter.x86_64-linux = pkgs.nixpkgs-fmt;
    };

  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
    extra-sandbox-paths = "/opt";
  };
}

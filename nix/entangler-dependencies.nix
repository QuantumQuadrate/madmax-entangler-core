{ python3Packages, lib }:

{
  dynaconf = python3Packages.buildPythonPackage rec {
    pname = "dynaconf";
    version = "3.1.7";
    src = python3Packages.fetchPypi {
      inherit pname version;
      sha256 = "e9d80b46ba4d9372f2f40c812594c963f74178140c0b596e57f2881001fc4d35";
    };

    propagatedBuildInputs = with python3Packages; [
      click
      python-box
      python-dotenv
      toml
    ];

    doCheck = false;

    meta = with lib; {
      homepage = "https://github.com/rochacbruno/dynaconf";
      description = "The dynamic configurator for your Python Project";
      license = licenses.mit;
    };
  };
}

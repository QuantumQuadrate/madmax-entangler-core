{ python3Packages, lib }:

{
  dynaconf = python3Packages.buildPythonPackage rec {
    pname = "dynaconf";
    version = "3.2.6";
    src = python3Packages.fetchPypi {
      inherit pname version;
      sha256 = "74cc1897396380bb957730eb341cc0976ee9c38bbcb53d3307c50caed0aedfb8";
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

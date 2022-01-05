{ python3Packages, lib }:

{
  dynaconf = python3Packages.buildPythonPackage rec {
    pname = "dynaconf";
    version = "2.2.2";
    src = python3Packages.fetchPypi {
      inherit pname version;
      sha256 = "4bac78b432e090d8ed66f1c23fb32e03ca91a590bf0a51ac36137e0e45ac31ca";
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

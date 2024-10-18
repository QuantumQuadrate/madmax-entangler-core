{ buildPythonPackage
, lib
  # python requirements
, pytestrunner
, numpy
, artiq
, dynaconf
  # gateware requirements
, buildGateware ? false
, jsonschema
, mergedeep
, migen ? null
, misoc ? null
, pytestCheckHook
}:


buildPythonPackage rec {
  pname = "entangler";
  version = "1.3.0";

  src = lib.cleanSource ./..;

  buildInputs = [ pytestrunner ];

  propagatedBuildInputs = [
    numpy
    artiq
    dynaconf
  ] ++ lib.optionals buildGateware [
    jsonschema # really a dependency of artiq.coredevice.jsondesc, but that's imported by entangler.kasli_generic so it's functionally a requirement
    mergedeep
    migen
    misoc
  ];

  dontWrapQtApps = true;

  doCheck = buildGateware; # all pytest tests are actually gateware tests, require migen
  checkInputs = [ pytestCheckHook ];
  pytestFlagsArray = [
    "-m 'not slow'"
  ];
  pythonImportsCheck = [ pname "${pname}.driver" ]
    ++ lib.optionals buildGateware [ "${pname}.kasli_generic" "${pname}.core" "${pname}.phy" ];

  meta = with lib; {
    description = "ARTIQ extension to generate & check patterns (for entanglement).";
    homepage = "https://github.com/drewrisinger/entangler-core/";
    license = licenses.gpl3;
    platforms = platforms.all;
    maintainers = with maintainers; [ drewrisinger ];
  };
}

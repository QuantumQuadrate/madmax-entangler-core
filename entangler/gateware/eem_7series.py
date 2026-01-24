from artiq.gateware.eem_7series import *

from entangler.kasli_generic import peripheral_entangler


def inject():
    """Inject custom peripheral types into the ARTIQ EEM 7 series gateware code."""
    peripheral_processors.update({
        'entangler': peripheral_entangler,
    })

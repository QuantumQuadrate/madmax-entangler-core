from __future__ import annotations

import json
import importlib.resources as r
from typing import Any

# NOTE: these imports are safe because they live in the entangler repo.
from entangler.config import settings as entangler_settings
import entangler.phy


def peripheral_entangler(
    description: dict[str, Any],
    core_device: Any,
    module: Any,
    rtio_clk_freq: float,
):
    """
    Called by ARTIQ kasli when it sees a peripheral with "type": "entangler".
    Must return an object (module) to be added to the gateware design.
    """
    # You will copy/adapt your EntanglerEEM class here (or import it if already exists)
    from .kasli_generic import EntanglerEEM  # <- adjust to your code

    return EntanglerEEM(
        core=core_device,
        core_module=module,
        phy_cls=entangler.phy.Entangler,
        # map your JSON fields -> constructor args
        ports=description["ports"],
        **entangler_settings,
    )


def merge_entangler_schema(base_schema_text: str) -> str:
    """
    Merge entangler JSON schema into ARTIQ base schema.
    Returns a schema text that ARTIQ can use.
    """
    # Store schema file in entangler package (next step)
    schema_text = r.files("entangler").joinpath("entangler_eem.schema.json").read_text()
    # We return both schemas as a merged JSON text,
    # but the actual merge function lives in ARTIQ.
    # So we return the entangler schema text and let wrapper call jsondesc.merge_schemas.
    return schema_text

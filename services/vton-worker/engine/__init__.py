"""VTON engine adapter layer.

The worker holds NO business logic (no storage, no auth, no DB, no frontend).
Its only job is to take a validated ``VTONJobRequest`` (person image + garments),
run the configured engine, and return a validated output image. Swapping the
engine is a config change (`VTON_ENGINE`) that selects the concrete subclass —
the surrounding CONFIT contract is unchanged.

Every engine must:
  * render(person_image, garment_image, category, ...) -> PIL.Image
  * validate_inputs(...)            # fail loudly on malformed/unsupported input
  * validate_output(...)            # no echo, not blank, valid decode, real change
  * metadata()                      # honest engine/model/revision/license

The engines are lazily imported so unit tests can import this module and assert
the adapter contract without GPU, torch, or weights installed.
"""

from .base import VTONEngine  # noqa: F401

__all__ = ["VTONEngine", "FashnSegfeeVTONEngine"]

# Registered engines by the canonical `VTON_ENGINE` string the server sends.
# NOTE: registration is optional/static; importing this module must never pull
# in torch or model weights, so tests can assert the adapter mix without a GPU.
_REGISTRY: dict[str, type[VTONEngine]] = {}


def register_engine(name: str, cls: type[VTONEngine]) -> None:
    _REGISTRY[name] = cls


def get_engine(name: str) -> type[VTONEngine] | None:
    """Return the engine class for a name, or None (never guesses)."""
    return _REGISTRY.get(name)


# Register the commercial engine. Keep `fashn_vton_segfee` as the production
# recommendation; the non-commercial CatVTON path is deliberately NOT registered
# here so the default deployment resolves to a commercially defensible engine.
from .fashn_segfee import FashnSegfeeVTONEngine  # noqa: E402

register_engine("fashn_vton_segfee", FashnSegfeeVTONEngine)

"""Registry of dialect adapters. Third parties can register their own."""
from __future__ import annotations

from ...model.profile import Dialect
from . import abusua, ga4gh, studio

_REGISTRY = {
    Dialect.GA4GH: ga4gh,
    Dialect.ABUSUA: abusua,
    Dialect.STUDIO: studio,
}


def get_adapter(dialect: str):
    try:
        return _REGISTRY[dialect]
    except KeyError:
        raise ValueError("unknown dialect: {!r} (known: {})".format(
            dialect, ", ".join(sorted(_REGISTRY))))


def register(dialect: str, module) -> None:
    _REGISTRY[dialect] = module


def known() -> list:
    return sorted(_REGISTRY)

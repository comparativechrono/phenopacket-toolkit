"""Conversions between dialects and serialization formats."""
from __future__ import annotations

from ..io import writers
from ..model.document import Document
from ..model.profile import Dialect


def to_dialect(doc: Document, dialect: str) -> str:
    """Serialise a Document to JSON in the requested dialect."""
    return writers.to_json_str(doc, dialect=dialect)


def to_format(doc: Document, fmt: str, *, dialect: str = Dialect.GA4GH) -> str:
    """Serialise to a derived format: json | ped | tsv (yaml via write())."""
    if fmt == "json":
        return writers.to_json_str(doc, dialect=dialect)
    if fmt == "ped":
        return writers.to_ped(doc)
    if fmt == "tsv":
        return writers.to_tsv(doc)
    raise ValueError("unsupported format {!r} (json|ped|tsv; yaml/jsonl via write)".format(fmt))

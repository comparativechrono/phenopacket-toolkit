"""Validation, by pedigree-ga4gh: the same checks every tool built on it applies.

The structural checks mirror phenopacket-tools, the Phenopackets team's
validator for Phenopackets v2 (its JSON schemas and its MetaData check); the GA4GH
Pedigree checks follow the standard's conceptual model. See
``pedigree_ga4gh.validate``.
"""
from __future__ import annotations

from pedigree_ga4gh import validate as _validate

from ..model.document import Document
from ..report.findings import Report


def validate(doc: Document, *, level: str = "all", online: bool = False) -> Report:
    """Check a Document. ``level`` and ``online`` are accepted for compatibility with 0.3 and ignored."""
    rep = Report()
    for f in _validate(doc.raw, kind=doc.kind):
        rep.add("standard", f.severity, f.code, f.message, path=f.path, fix=f.fix)
    return rep

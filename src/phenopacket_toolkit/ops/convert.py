"""Conversions: between a GA4GH Pedigree and a Phenopackets Family, and to PED or TSV."""
from __future__ import annotations

from typing import List, Optional, Tuple

from pedigree_ga4gh import from_document, to_ga4gh_pedigree, to_phenopackets_family

from ..io import writers
from ..model.document import Document
from ..model.profile import SourceProfile

CREATED_BY = "phenotk convert"


def to_kind(doc: Document, kind: str, *, created_by: str = CREATED_BY,
            proband_id: Optional[str] = None) -> Tuple[Document, List[str]]:
    """Turn a Family into a GA4GH Pedigree (``kind="pedigree"``) or the reverse
    (``kind="family"``), through pedigree-ga4gh. Returns (document, warnings)."""
    k, warnings = from_document(doc.raw)
    if kind == "pedigree":
        data, w = to_ga4gh_pedigree(k, created_by=created_by)
    elif kind == "family":
        data, w = to_phenopackets_family(k, created_by=created_by, proband_id=proband_id)
    else:
        raise ValueError("kind must be 'pedigree' or 'family'")
    return Document(data, SourceProfile()), warnings + w


def to_format(doc: Document, fmt: str) -> str:
    """Serialise to a derived format: json | ped | tsv (yaml and jsonl via write())."""
    if fmt == "json":
        return writers.to_json_str(doc)
    if fmt == "ped":
        return writers.to_ped(doc)
    if fmt == "tsv":
        return writers.to_tsv(doc)
    raise ValueError("unsupported format {!r} (json|ped|tsv; yaml/jsonl via write)".format(fmt))

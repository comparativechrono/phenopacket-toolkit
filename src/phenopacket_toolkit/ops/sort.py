"""Canonical ordering of a Document for reproducible diffs."""
from __future__ import annotations

from ..model.document import Document


def sort_document(doc: Document) -> Document:
    out = doc.copy()
    raw = out.raw

    if isinstance(raw.get("relatives"), list):
        raw["relatives"].sort(key=lambda pp: pp.get("subject", {}).get("id", ""))
    for key in ("individuals", "members"):
        if isinstance(raw.get(key), list):
            raw[key].sort(key=lambda pp: (pp.get("subject") or {}).get("id", ""))
    if isinstance(raw.get("relationships"), list):
        raw["relationships"].sort(key=lambda r: (r.get("individualId", ""), (r.get("relation") or {}).get("id", ""),
                                                 r.get("relativeId", "")))

    if isinstance(raw.get("pedigree"), dict):
        persons = raw["pedigree"].get("persons")
        if isinstance(persons, list):
            persons.sort(key=lambda p: p.get("individualId", ""))

    for pp in out.phenopackets():
        feats = pp.raw.get("phenotypicFeatures")
        if isinstance(feats, list):
            feats.sort(key=lambda f: (f.get("type", {}).get("id", ""),
                                      f.get("type", {}).get("label", "")))
        dis = pp.raw.get("diseases")
        if isinstance(dis, list):
            dis.sort(key=lambda d: (d.get("term", {}).get("id", ""),
                                    d.get("term", {}).get("label", "")))
    return out

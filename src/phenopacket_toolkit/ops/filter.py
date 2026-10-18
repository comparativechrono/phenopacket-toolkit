"""Subset a Document: keep/drop terms and individuals."""
from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Set

from ..model.curie import normalise_prefix
from ..model.document import Document


def filter_document(
    doc: Document,
    *,
    terms: Optional[Iterable[str]] = None,
    include_descendants: bool = False,
    descendant_resolver: Optional[Callable[[str], Set[str]]] = None,
    observed_only: bool = False,
    excluded_only: bool = False,
    affected_only: bool = False,
    proband_only: bool = False,
    sex: Optional[str] = None,
    id_list: Optional[Iterable[str]] = None,
    invert: bool = False,
    prune_pedigree: bool = False,
) -> Document:
    """Return a new Document keeping only matching terms/individuals.

    Term filters act on terms; individual filters act on whole phenopackets.
    ``invert`` flips term membership (drop the matched terms instead of keep).
    """
    out = doc.copy()

    wanted: Optional[Set[str]] = None
    if terms:
        wanted = {normalise_prefix(t) for t in terms}
        if include_descendants:
            expanded = set(wanted)
            for t in list(wanted):
                if descendant_resolver is not None:
                    expanded |= {normalise_prefix(x) for x in descendant_resolver(t)}
            wanted = expanded

    keep_ids: Optional[Set[str]] = set(id_list) if id_list else None

    # --- individual-level pruning ---
    def keep_packet(role: str, subject: dict, ped_aff: str) -> bool:
        if proband_only and role != "proband":
            return False
        if sex and (subject.get("sex") != sex):
            return False
        if keep_ids is not None and subject.get("id") not in keep_ids:
            return False
        if affected_only and ped_aff and ped_aff != "AFFECTED":
            return False
        return True

    aff_by_id = out.affected_status()
    ped = out.pedigree()
    before = {pp.subject.id for pp in out.phenopackets()}

    raw = out.raw
    if out.kind == "family":
        prob = raw.get("proband")
        if isinstance(prob, dict):
            sid = prob.get("subject", {}).get("id", "")
            if not keep_packet("proband", prob.get("subject", {}), aff_by_id.get(sid, "")):
                # a Family must have its proband
                raise ValueError("these filters leave out the proband ({}), and a Phenopackets Family must have "
                                 "one. Filter the GA4GH Pedigree instead, or split the Family into a Phenopacket "
                                 "for each person (phenotk split)".format(sid or "?"))
        if "relatives" in raw:
            raw["relatives"] = [rel for rel in raw.get("relatives", []) or []
                                if keep_packet("relative", rel.get("subject", {}),
                                               aff_by_id.get(rel.get("subject", {}).get("id", ""), ""))]
    elif out.kind in ("pedigree", "cohort"):
        key = "individuals" if out.kind == "pedigree" else "members"
        index = set(raw.get("indexPatients") or [])
        kept = []
        for m in raw.get(key, []) or []:
            sid = (m.get("subject") or {}).get("id", "")
            role = "proband" if sid in index else "relative"
            if keep_packet(role, m.get("subject", {}), aff_by_id.get(sid, "")):
                kept.append(m)
        raw[key] = kept
        if out.kind == "pedigree":
            ids = {(m.get("subject") or {}).get("id") for m in kept}
            if "relationships" in raw:
                raw["relationships"] = [r for r in raw["relationships"]
                                        if r.get("individualId") in ids and r.get("relativeId") in ids]
            if "indexPatients" in raw:
                raw["indexPatients"] = [i for i in raw["indexPatients"] if i in ids]

    # --- term-level pruning ---
    if wanted is not None or observed_only or excluded_only:
        for pp in out.phenopackets():
            _filter_terms(pp.raw, wanted, invert, observed_only, excluded_only)

    # --- optional pedigree pruning ---
    # A Family's pedigree loses the people whose Phenopackets the filters left out, and any line to them, so that
    # it stays valid. (The people of the pedigree who never had a Phenopacket – relatives with nothing to record –
    # are not left out by a filter, and stay.) A GA4GH Pedigree's relationships are pruned above, always.
    if prune_pedigree and ped is not None:
        removed = before - {pp.subject.id for pp in out.phenopackets()}
        persons = raw.get("pedigree", {}).get("persons", [])
        kept = [p for p in persons if p.get("individualId") not in removed]
        for p in kept:
            for key in ("paternalId", "maternalId"):
                if p.get(key) in removed:
                    p[key] = "0"
        raw["pedigree"]["persons"] = kept

    return out


def _term_matches(term_id: str, wanted: Optional[Set[str]]) -> bool:
    if wanted is None:
        return True
    return normalise_prefix(term_id) in wanted


def _filter_terms(packet: dict, wanted, invert, observed_only, excluded_only) -> None:
    for list_key, term_key in (("phenotypicFeatures", "type"), ("diseases", "term")):
        items = packet.get(list_key)
        if not items:
            continue
        kept = []
        for item in items:
            term = item.get(term_key, {}) if isinstance(item, dict) else {}
            excluded = bool(item.get("excluded", False))
            if observed_only and excluded:
                continue
            if excluded_only and not excluded:
                continue
            if wanted is not None:
                match = _term_matches(term.get("id", ""), wanted)
                if match == invert:   # keep on match unless inverted
                    continue
            kept.append(item)
        packet[list_key] = kept

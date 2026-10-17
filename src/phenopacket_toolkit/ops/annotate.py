"""Add fields to selected phenopackets: the enrichment a pedigree never carries.

Target selection (``target`` argument):
  * "proband"            - the proband phenopacket
  * "all"                - every phenopacket
  * "affected" / "unaffected" - by pedigree affectedStatus
  * a subject id, or a list/iterable of subject ids
"""
from __future__ import annotations

import copy
import json
from typing import Iterable, List, Optional, Union

from ..model import builders as B
from ..model.document import Document

Target = Union[str, Iterable[str]]


# -- target resolution ----------------------------------------------------
def resolve_targets(doc: Document, target: Target) -> List[dict]:
    packets = list(doc.phenopackets())

    if isinstance(target, str):
        if target == "all":
            return [pp.raw for pp in packets]
        if target == "proband":
            return [pp.raw for pp in packets if pp.role == "proband"]
        if target in ("affected", "unaffected"):
            want = "AFFECTED" if target == "affected" else "UNAFFECTED"
            ped = doc.pedigree()
            aff = {p.individual_id: p.affected_status for p in ped.persons} if ped else {}
            return [pp.raw for pp in packets if aff.get(pp.subject.id) == want]
        ids = {target}
    else:
        ids = set(target)
    return [pp.raw for pp in packets if pp.subject.id in ids]


# -- generic path setter --------------------------------------------------
def _tokens(path: str):
    out = []
    for part in path.split("."):
        m = part.split("[")
        key = m[0]
        if key:
            out.append(("key", key))
        for idx in m[1:]:
            out.append(("idx", int(idx.rstrip("]"))))
    return out


def _apply_path(obj: dict, path: str, value, mode: str) -> None:
    toks = _tokens(path)
    cur = obj
    for i, (kind, tok) in enumerate(toks):
        last = i == len(toks) - 1
        if kind == "key":
            if last:
                if mode == "append":
                    cur.setdefault(tok, [])
                    if not isinstance(cur[tok], list):
                        raise ValueError("cannot append to non-list at {!r}".format(path))
                    cur[tok].append(value)
                elif mode == "merge" and isinstance(cur.get(tok), dict) and isinstance(value, dict):
                    cur[tok].update(value)
                else:
                    cur[tok] = value
            else:
                cur = cur.setdefault(tok, {})
        else:  # index into a list
            lst = cur if isinstance(cur, list) else None
            if lst is None:
                raise ValueError("index used on non-list at {!r}".format(path))
            cur = lst[tok]


# -- the operation --------------------------------------------------------
def add(
    doc: Document,
    target: Target = "proband",
    *,
    # typed conveniences
    phenotypes: Optional[List[dict]] = None,     # each: {"id","label",...} per builder kwargs
    diseases: Optional[List[dict]] = None,
    measurements: Optional[List[dict]] = None,
    interpretations: Optional[List[dict]] = None,
    external_references: Optional[List[dict]] = None,
    files: Optional[List[dict]] = None,
    vital_status: Optional[dict] = None,
    subject_fields: Optional[dict] = None,       # e.g. {"dateOfBirth":..., "karyotypicSex":...}
    # generic escape hatches
    set_paths: Optional[List[tuple]] = None,     # (path, value)
    merge_paths: Optional[List[tuple]] = None,
    append_paths: Optional[List[tuple]] = None,
    patch: Optional[dict] = None,                # deep-merge an arbitrary object into each target
) -> Document:
    out = doc.copy()
    targets = resolve_targets(out, target)
    if not targets:
        raise ValueError("no phenopackets matched target {!r}".format(target))

    for pkt in targets:
        if phenotypes:
            pkt.setdefault("phenotypicFeatures", []).extend(
                B.phenotypic_feature(**p) for p in phenotypes)
        if diseases:
            pkt.setdefault("diseases", []).extend(B.disease(**d) for d in diseases)
        if measurements:
            pkt.setdefault("measurements", []).extend(B.measurement(**m) for m in measurements)
        if interpretations:
            added = copy.deepcopy(interpretations)
            # a genomic interpretation is of this person, unless it says whose it is
            sid = (pkt.get("subject") or {}).get("id", "")
            for interp in added:
                for gi in ((interp.get("diagnosis") or {}).get("genomicInterpretations") or []):
                    if not gi.get("subjectOrBiosampleId"):
                        gi["subjectOrBiosampleId"] = sid
            pkt.setdefault("interpretations", []).extend(added)
        if external_references:
            md = pkt.setdefault("metaData", {})
            md.setdefault("externalReferences", []).extend(copy.deepcopy(external_references))
        if files:
            pkt.setdefault("files", []).extend(copy.deepcopy(files))
        if vital_status is not None:
            pkt.setdefault("subject", {})["vitalStatus"] = copy.deepcopy(vital_status)
        if subject_fields:
            pkt.setdefault("subject", {}).update(copy.deepcopy(subject_fields))
        for p, v in (set_paths or []):
            _apply_path(pkt, p, v, "set")
        for p, v in (merge_paths or []):
            _apply_path(pkt, p, v, "merge")
        for p, v in (append_paths or []):
            _apply_path(pkt, p, v, "append")
        if patch:
            _deep_merge(pkt, copy.deepcopy(patch))

    # the terms added may come from ontologies the file did not use yet: declare them in metaData (and nothing
    # else changes in a file in the standard form)
    from pedigree_ga4gh import upgrade
    out.raw, _changes, _todo = upgrade(out.raw, created_by="phenotk add")
    return out


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        elif isinstance(v, list) and isinstance(dst.get(k), list):
            dst[k].extend(v)
        else:
            dst[k] = v

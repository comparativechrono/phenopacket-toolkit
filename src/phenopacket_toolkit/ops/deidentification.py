"""De-identification: scrub PII and remap identifiers consistently."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..model.document import Document


@dataclass
class DeidResult:
    document: Document
    crosswalk: Dict[str, str] = field(default_factory=dict)   # old id -> new id
    warnings: List[str] = field(default_factory=list)


def _collect_individual_ids(doc: Document) -> List[str]:
    """Every distinct individual id, in stable first-seen order."""
    order: List[str] = []
    seen = set()

    def add(x):
        if x and x not in seen and x != "0":
            seen.add(x)
            order.append(x)

    ped = doc.pedigree()
    if ped is not None:
        for p in ped.persons:
            add(p.individual_id)
    for pp in doc.phenopackets():
        add(pp.subject.id)
    return order


def _make_mapping(ids: List[str], scheme: str, salt: Optional[str]) -> Dict[str, str]:
    mapping = {}
    for i, old in enumerate(ids, 1):
        if scheme == "hash":
            h = hashlib.sha256(((salt or "") + old).encode("utf-8")).hexdigest()[:12]
            mapping[old] = "IND-" + h
        else:  # sequential
            mapping[old] = "IND-{:04d}".format(i)
    return mapping


def _remap_token(value: str, mapping: Dict[str, str]) -> str:
    if value in mapping:
        return mapping[value]
    return value


def _remap_wrapper_id(value: str, mapping: Dict[str, str]) -> str:
    # Family wrapper ids look like "FAM1-bob"; remap the trailing individual id.
    for old, new in mapping.items():
        if value == old:
            return new
        if value.endswith("-" + old):
            return value[: -len(old)] + new
    return value


def deidentify(
    doc: Document,
    *,
    remap_ids: Optional[str] = "seq",   # "seq" | "hash" | None
    salt: Optional[str] = None,
    drop_dob: bool = True,
    bin_age: Optional[str] = None,
    drop_names: bool = True,
    drop_provenance: bool = False,
) -> DeidResult:
    out = doc.copy()
    warnings: List[str] = []
    crosswalk: Dict[str, str] = {}

    if remap_ids:
        ids = _collect_individual_ids(out)
        crosswalk = _make_mapping(ids, remap_ids, salt)
        _apply_remap(out, crosswalk)
        _verify_graph(out, warnings)

    for pp in out.phenopackets():
        subj = pp.subject.raw
        if drop_dob:
            subj.pop("dateOfBirth", None)
        if bin_age:
            _generalise_age(subj, bin_age, warnings)
        if drop_names:
            subj.pop("alternateIds", None)
            subj.pop("alternate_ids", None)
        if drop_provenance:
            md = pp.raw.get("metaData")
            if isinstance(md, dict):
                md.pop("createdBy", None)
                md.pop("created", None)

    if drop_provenance and isinstance(out.raw.get("metaData"), dict):
        out.raw["metaData"].pop("createdBy", None)
        out.raw["metaData"].pop("created", None)

    return DeidResult(document=out, crosswalk=crosswalk, warnings=warnings)


def _apply_remap(doc: Document, mapping: Dict[str, str]) -> None:
    raw = doc.raw
    # pedigree
    ped = raw.get("pedigree", {})
    for p in ped.get("persons", []) or []:
        p["individualId"] = _remap_token(p.get("individualId", ""), mapping)
        if p.get("paternalId") not in (None, "0"):
            p["paternalId"] = _remap_token(p["paternalId"], mapping)
        if p.get("maternalId") not in (None, "0"):
            p["maternalId"] = _remap_token(p["maternalId"], mapping)
    # phenopackets: subject id + wrapper id
    for pp in doc.phenopackets():
        subj = pp.subject.raw
        subj["id"] = _remap_token(subj.get("id", ""), mapping)
        if "id" in pp.raw:
            pp.raw["id"] = _remap_wrapper_id(pp.raw["id"], mapping)


def _verify_graph(doc: Document, warnings: List[str]) -> None:
    ped = doc.pedigree()
    if ped is None:
        return
    ids = {p.individual_id for p in ped.persons}
    for p in ped.persons:
        for role, pid in (("paternalId", p.paternal_id), ("maternalId", p.maternal_id)):
            if pid and pid != "0" and pid not in ids:
                warnings.append(
                    "after remap, {} {!r} of {!r} no longer resolves".format(
                        role, pid, p.individual_id))


def _generalise_age(subject: dict, bin_spec: str, warnings: List[str]) -> None:
    """Round an ISO8601 age in timeAtLastEncounter down to a bin (e.g. '5y')."""
    tae = subject.get("timeAtLastEncounter")
    if not isinstance(tae, dict):
        return
    age = tae.get("age", {})
    iso = age.get("iso8601duration") if isinstance(age, dict) else None
    if not iso or not bin_spec.endswith("y"):
        return
    try:
        years = int(iso.lstrip("P").rstrip("Y").split("Y")[0])
        width = int(bin_spec[:-1])
        binned = (years // width) * width
        age["iso8601duration"] = "P{}Y".format(binned)
    except (ValueError, AttributeError):
        warnings.append("could not generalise age {!r}".format(iso))

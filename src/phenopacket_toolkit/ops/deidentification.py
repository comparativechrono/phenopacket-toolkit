"""De-identification: scrub PII and remap identifiers consistently."""
from __future__ import annotations

import hashlib
import re
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
    for r in doc.relationships():
        add(r.individual)
        add(r.relative)
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


def _remap_wrapper_id(value: str, old: str, new: str) -> str:
    # Phenopacket ids written by pedigree-ga4gh look like "FAM1-II-3": the family id,
    # a hyphen, then the subject id. Swap the trailing subject id.
    if value == old:
        return new
    if old and value.endswith("-" + old):
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
        _remap_narrative(out, crosswalk, warnings)

    for pp in out.phenopackets():
        subj = pp.subject.raw
        if drop_dob:
            subj.pop("dateOfBirth", None)
        if bin_age:
            _generalise_age(subj, bin_age, warnings)
        if drop_names:
            subj.pop("alternateIds", None)
        if drop_provenance:
            _hide_provenance(pp.raw.get("metaData"))

    if drop_provenance:
        _hide_provenance(out.raw.get("metaData"))

    return DeidResult(document=out, crosswalk=crosswalk, warnings=warnings)


def _apply_remap(doc: Document, mapping: Dict[str, str]) -> None:
    raw = doc.raw
    ped = raw.get("pedigree", {}) if doc.kind == "family" else {}
    for p in ped.get("persons", []) or []:
        p["individualId"] = _remap_token(p.get("individualId", ""), mapping)
        if p.get("paternalId") not in (None, "0"):
            p["paternalId"] = _remap_token(p["paternalId"], mapping)
        if p.get("maternalId") not in (None, "0"):
            p["maternalId"] = _remap_token(p["maternalId"], mapping)
    for r in raw.get("relationships", []) or [] if doc.kind == "pedigree" else []:
        r["individualId"] = _remap_token(r.get("individualId", ""), mapping)
        r["relativeId"] = _remap_token(r.get("relativeId", ""), mapping)
    if doc.kind == "pedigree" and raw.get("indexPatients"):
        raw["indexPatients"] = [_remap_token(x, mapping) for x in raw["indexPatients"]]
    for pp in doc.phenopackets():
        subj = pp.subject.raw
        old = subj.get("id", "")
        new = _remap_token(old, mapping)
        subj["id"] = new
        if "id" in pp.raw:
            pp.raw["id"] = _remap_wrapper_id(pp.raw["id"], old, new)
        for bs in pp.raw.get("biosamples", []) or []:
            if bs.get("individualId"):
                bs["individualId"] = _remap_token(bs["individualId"], mapping)
        for interp in pp.raw.get("interpretations", []) or []:
            for gi in ((interp.get("diagnosis") or {}).get("genomicInterpretations") or []):
                if gi.get("subjectOrBiosampleId"):
                    gi["subjectOrBiosampleId"] = _remap_token(gi["subjectOrBiosampleId"], mapping)
        for f in pp.raw.get("files", []) or []:
            ids = f.get("individualToFileIdentifiers")
            if isinstance(ids, dict):
                f["individualToFileIdentifiers"] = {_remap_token(k, mapping): v for k, v in ids.items()}


DEIDENTIFIED_BY = "phenotk deidentify"


def _hide_provenance(md) -> None:
    """Who made the file and when, replaced by the de-identification itself: ``created`` and ``createdBy`` are
    required in metaData, so they cannot just be removed. The record of updates, and who submitted the file, go."""
    if not isinstance(md, dict):
        return
    from pedigree_ga4gh.phenopackets import now
    md["created"] = now()
    md["createdBy"] = DEIDENTIFIED_BY
    md.pop("updates", None)
    md.pop("submittedBy", None)


def _remap_narrative(doc: Document, mapping: Dict[str, str], warnings: List[str]) -> None:
    """A GA4GH Pedigree's narrative is free text that names people by their ids ("proband IV-3"): the ids in it are
    replaced too, each as a whole word (II-1 is not part of III-1). Ids that are bare numbers could be any number in
    the text, so then the narrative is left as it is, with a warning."""
    text = doc.raw.get("narrative") if doc.kind == "pedigree" else None
    if not isinstance(text, str) or not text.strip() or not mapping:
        return
    if any(k.isdigit() for k in mapping):
        warnings.append("the narrative was left as it is, because some ids are bare numbers: it may name people by "
                        "their old ids, so read it (or remove it) before sharing the file")
        return
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")(?![\w-])")
    new = pattern.sub(lambda m: mapping[m.group(1)], text)
    doc.raw["narrative"] = new
    warnings.append("the narrative is free text: the ids in it were replaced, but read it before sharing the file")


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

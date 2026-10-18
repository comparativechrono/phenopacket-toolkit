"""Split a Family into per-individual phenopackets; merge phenopackets/families."""
from __future__ import annotations

import copy
from typing import Dict, List, Optional

from ..model.document import Document
from ..model.profile import SourceProfile
from pedigree_ga4gh import upgrade as _upgrade


def split(doc: Document, *, affected_only: bool = False) -> List[Document]:
    """Return one standalone-Phenopacket Document per contained phenopacket."""
    out: List[Document] = []
    aff_by_id = doc.affected_status()
    for pp in doc.phenopackets():
        if affected_only and aff_by_id.get(pp.subject.id) != "AFFECTED":
            continue
        packet = copy.deepcopy(pp.raw)
        if not packet.get("metaData") and doc.metadata:
            packet["metaData"] = copy.deepcopy(doc.metadata)
        packet, _changes, _todo = _upgrade(packet, created_by="phenotk split")
        out.append(Document(packet, SourceProfile()))
    return out


def merge(docs: List[Document], *, into: str = "cohort", cohort_id: str = "cohort",
          notes: Optional[List[str]] = None) -> Document:
    """Merge several Documents into a single Cohort (default) or Family.

    People are told apart by their subject ids. In a Family, the same id is the same person: the first
    Phenopacket for it is kept. In a Cohort, the same id in two files is taken to be two people (pedigree numbers
    such as IV-3 recur from family to family), and the later one is renamed after its file's id ("LYNCH-IV-3").
    Either is reported in ``notes``, when a list is given.

    A Family's pedigree comes from the inputs: the pedigree of each Family among them, and the parents worked out
    from each GA4GH Pedigree's relationships. Members found in none of them are added as founders. The metaData
    keeps a resource, with its release, for every ontology any input declares."""
    notes = notes if notes is not None else []
    members: List[dict] = []
    owner: Dict[str, int] = {}       # subject id -> the input it came from
    for n, d in enumerate(docs):
        for pp in d.phenopackets():
            packet = copy.deepcopy(pp.raw)
            sid = (packet.get("subject") or {}).get("id", "")
            if sid and sid in owner:
                if into == "family":
                    notes.append("{} is in more than one file: the first Phenopacket for {} was kept".format(sid, sid))
                    continue
                if owner[sid] != n:
                    new = _unique("{}-{}".format(d.id or "file{}".format(n + 1), sid), owner)
                    packet["subject"]["id"] = new
                    if packet.get("id"):
                        packet["id"] = "{}-{}".format(d.id, new) if d.id and not new.startswith(d.id + "-") else new
                    notes.append("{} in {} was renamed {}: another file has a person with that id".format(
                        sid, d.id or "file {}".format(n + 1), new))
                    sid = new
            if sid:
                owner[sid] = n
            members.append(packet)

    if into == "cohort":
        data = {"id": cohort_id, "members": members, "metaData": _merged_md(docs)}
    elif into == "family":
        if not members:
            raise ValueError("nothing to merge")
        known = _pedigree_persons(docs, cohort_id)
        persons = list(known.values())
        for m in members:
            sid = (m.get("subject") or {}).get("id", "")
            if sid and sid not in known:
                persons.append({"familyId": cohort_id, "individualId": sid, "paternalId": "0", "maternalId": "0",
                                "sex": (m.get("subject") or {}).get("sex", "UNKNOWN_SEX"),
                                "affectedStatus": "AFFECTED" if (m.get("diseases") or m.get("phenotypicFeatures"))
                                else "MISSING"})
                known[sid] = persons[-1]
        # (whether the proband's parents are related: as the first Family among the inputs says)
        consang = next((bool(d.raw.get("consanguinousParents")) for d in docs if d.kind == "family"), False)
        data = {"id": cohort_id, "proband": members[0], "relatives": members[1:],
                "consanguinousParents": consang, "pedigree": {"persons": persons}, "metaData": _merged_md(docs)}
    else:
        raise ValueError("into must be 'cohort' or 'family'")
    data, _changes, _todo = _upgrade(data, created_by="phenotk merge")
    return Document(data, SourceProfile())


def _unique(name: str, taken: Dict[str, int]) -> str:
    out, i = name, 2
    while out in taken:
        out, i = "{}_{}".format(name, i), i + 1
    return out


def _pedigree_persons(docs: List[Document], family_id: str) -> Dict[str, dict]:
    """individual id -> its PED-style pedigree person, from the Families' pedigrees and the GA4GH Pedigrees'
    relationships among the inputs (the first input to mention a person wins)"""
    persons: Dict[str, dict] = {}
    for d in docs:
        if d.kind == "family":
            ped = d.pedigree()
            for p in ped.persons if ped is not None else []:
                if p.individual_id and p.individual_id not in persons:
                    persons[p.individual_id] = dict(copy.deepcopy(p.raw), familyId=family_id)
        elif d.kind == "pedigree":
            from pedigree_ga4gh import from_ga4gh_pedigree
            k, _warnings = from_ga4gh_pedigree(d.raw)
            aff = d.affected_status()
            for m in k.members:
                if m.id in persons:
                    continue
                father, mother, _notes = k.genetic_parents(m.id)
                persons[m.id] = {"familyId": family_id, "individualId": m.id, "paternalId": father or "0",
                                 "maternalId": mother or "0", "sex": m.sex or "UNKNOWN_SEX",
                                 "affectedStatus": aff.get(m.id, "MISSING")}
    return persons


def _merged_md(docs: List[Document]) -> dict:
    """the first input's metaData, with a resource for every ontology that any input (or any Phenopacket in it)
    declares, keeping the releases that are known"""
    md = _first_md(docs)
    res: Dict[str, dict] = {}

    def known(r):
        return r.get("version") not in (None, "", "unknown")

    for d in docs:
        for src in [d.metadata] + [pp.raw.get("metaData") for pp in d.phenopackets()]:
            for r in (src or {}).get("resources") or []:
                pre = r.get("namespacePrefix") if isinstance(r, dict) else None
                if pre and (pre not in res or (known(r) and not known(res[pre]))):
                    res[pre] = copy.deepcopy(r)
    if res:
        md["resources"] = list(res.values())
    return md


def _first_md(docs: List[Document]) -> dict:
    for d in docs:
        if d.metadata:
            return copy.deepcopy(d.metadata)
    return {}

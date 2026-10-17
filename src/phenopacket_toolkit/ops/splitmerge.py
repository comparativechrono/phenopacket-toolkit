"""Split a Family into per-individual phenopackets; merge phenopackets/families."""
from __future__ import annotations

import copy
from typing import List

from ..model.document import Document
from ..model.profile import SourceProfile


def split(doc: Document, *, affected_only: bool = False) -> List[Document]:
    """Return one standalone-Phenopacket Document per contained phenopacket."""
    out: List[Document] = []
    aff_by_id = {}
    ped = doc.pedigree()
    if ped is not None:
        aff_by_id = {p.individual_id: p.affected_status for p in ped.persons}
    for pp in doc.phenopackets():
        if affected_only and aff_by_id.get(pp.subject.id) != "AFFECTED":
            continue
        packet = copy.deepcopy(pp.raw)
        packet.pop("_ppktk_inherited_metadata", None)
        if not packet.get("metaData") and doc.metadata:
            packet["metaData"] = copy.deepcopy(doc.metadata)
        out.append(Document(packet, SourceProfile(dialect=doc.source.dialect)))
    return out


def merge(docs: List[Document], *, into: str = "cohort", cohort_id: str = "cohort") -> Document:
    """Merge several Documents into a single Cohort (default) or Family."""
    members: List[dict] = []
    for d in docs:
        for pp in d.phenopackets():
            members.append(copy.deepcopy(pp.raw))

    if into == "cohort":
        data = {"id": cohort_id, "members": members, "metaData": _first_md(docs)}
    elif into == "family":
        data = {
            "id": cohort_id,
            "proband": members[0] if members else {},
            "relatives": members[1:],
            "metaData": _first_md(docs),
        }
    else:
        raise ValueError("into must be 'cohort' or 'family'")
    return Document(data, SourceProfile(dialect=docs[0].source.dialect if docs else "ga4gh"))


def _first_md(docs: List[Document]) -> dict:
    for d in docs:
        if d.metadata:
            return copy.deepcopy(d.metadata)
    return {}

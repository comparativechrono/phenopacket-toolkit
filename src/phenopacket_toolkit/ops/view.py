"""Render a Document as a readable table."""
from __future__ import annotations

from ..model.document import Document


def render(doc: Document, *, show_terms: bool = True) -> str:
    lines = []
    lines.append("{}  [{}]  dialect={}".format(
        doc.id or "<no id>", doc.kind, doc.source.dialect))
    if doc.source.adaptations:
        for a in doc.source.adaptations:
            lines.append("  ~ {}".format(a))

    aff_by_id = {}
    sex_by_id = {}
    ped = doc.pedigree()
    if ped is not None:
        for p in ped.persons:
            aff_by_id[p.individual_id] = p.affected_status
            sex_by_id[p.individual_id] = p.sex

    for pp in doc.phenopackets():
        sid = pp.subject.id
        marker = "*" if pp.role == "proband" else " "
        aff = aff_by_id.get(sid, "")
        sex = pp.subject.sex or sex_by_id.get(sid, "")
        head = "{} {:<14} {:<7} {:<11}".format(marker, sid, sex, aff)
        terms = list(pp.term_refs())
        if show_terms and terms:
            rendered = []
            for ref in terms:
                tag = "!" if ref.excluded else ""
                cid = ref.id or "(no-id)"
                rendered.append("{}{} {}".format(tag, cid, ref.label))
            head += "  " + "; ".join(rendered)
        lines.append(head.rstrip())

    if ped is not None:
        extra = [p.individual_id for p in ped.persons
                 if p.individual_id not in {pp.subject.id for pp in doc.phenopackets()}]
        if extra:
            lines.append("  pedigree-only individuals: {}".format(", ".join(extra)))
    return "\n".join(lines)

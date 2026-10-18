"""Render a Document as a readable table."""
from __future__ import annotations

from ..model.document import Document


def render(doc: Document, *, show_terms: bool = True) -> str:
    lines = ["{}  [{}]".format(doc.id or "<no id>", doc.kind_name)]
    for a in doc.source.adaptations:
        lines.append("  ~ {}".format(a))
    aff_by_id = doc.affected_status()
    sex_by_id = {}
    ped = doc.pedigree()
    if ped is not None:
        for p in ped.persons:
            sex_by_id[p.individual_id] = p.sex
    for pp in doc.phenopackets():
        sid = pp.subject.id
        marker = "*" if pp.role == "proband" else " "
        sex = pp.subject.sex or sex_by_id.get(sid, "")
        vital = (pp.subject.vital_status or {}).get("status", "") if isinstance(pp.subject.vital_status, dict) else ""
        head = "{} {:<14} {:<11} {:<10} {:<9}".format(marker, sid, sex, aff_by_id.get(sid, ""),
                                                     "deceased" if vital == "DECEASED" else "")
        terms = list(pp.term_refs())
        if show_terms and terms:
            rendered = []
            for ref in terms:
                tag = "not " if ref.excluded else ""
                rendered.append("{}{} {}".format(tag, ref.id or "(no id)", ref.label))
            head += "  " + "; ".join(rendered)
        lines.append(head.rstrip())
    if ped is not None:
        extra = [p.individual_id for p in ped.persons
                 if p.individual_id not in {pp.subject.id for pp in doc.phenopackets()}]
        if extra:
            lines.append("  in the pedigree without a Phenopacket: {}".format(", ".join(extra)))
    rels = doc.relationships()
    if rels:
        lines.append("")
        lines.append("relationships:")
        for r in rels:
            lines.append("  {} {} {}".format(r.individual, r.relation_label or r.relation_id, r.relative))
    return "\n".join(lines)

"""Write Documents out, and derive PED and TSV tables from them."""
from __future__ import annotations

import copy
import json
from typing import List

from ..model.document import Document

_SEX_TO_PED = {"MALE": "1", "FEMALE": "2"}
_AFF_TO_PED = {"AFFECTED": "2", "UNAFFECTED": "1"}


def to_json_str(doc: Document, *, indent=2) -> str:
    return json.dumps(doc.raw, indent=indent, ensure_ascii=False)


def write(doc: Document, path: str, *, fmt: str = "json", indent: int = 2) -> None:
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("YAML needs PyYAML: pip install 'phenopacket-toolkit[yaml]'")
        text = yaml.safe_dump(copy.deepcopy(doc.raw), sort_keys=False, allow_unicode=True)
    else:
        text = to_json_str(doc, indent=indent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def write_many(docs: List[Document], path: str) -> None:
    """Write newline-delimited JSON (one compact Document per line)."""
    with open(path, "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(to_json_str(d, indent=None))
            fh.write("\n")


def to_ped(doc: Document) -> str:
    """A six-column PED file.

    A Family's own PED-style pedigree is used as it is. For a GA4GH Pedigree the
    parents come from its relationships, read the same way pedigree-ga4gh reads
    them for a Family; people with no parents recorded are founders (0 0).
    """
    rows = []
    if doc.kind == "family":
        ped = doc.pedigree()
        if ped is None:
            return ""
        fam = doc.id or "FAM"
        for person in ped.persons:
            rows.append([person.raw.get("familyId", fam), person.individual_id, person.paternal_id or "0",
                         person.maternal_id or "0", _SEX_TO_PED.get(person.sex, "0"),
                         _AFF_TO_PED.get(person.affected_status, "0")])
    elif doc.kind == "pedigree":
        from pedigree_ga4gh import from_ga4gh_pedigree
        k, _ = from_ga4gh_pedigree(doc.raw)
        aff = doc.affected_status()
        for m in k.members:
            father, mother, _notes = k.genetic_parents(m.id)
            rows.append([k.id, m.id, father or "0", mother or "0", _SEX_TO_PED.get(m.sex, "0"),
                         _AFF_TO_PED.get(aff.get(m.id, "MISSING"), "0")])
    else:
        fam = doc.id or "FAM"
        for pp in doc.phenopackets():
            rows.append([fam, pp.subject.id, "0", "0", _SEX_TO_PED.get(pp.subject.sex or "", "0"),
                         _AFF_TO_PED.get(doc.affected_status().get(pp.subject.id, "MISSING"), "0")])
    return "".join("\t".join(r) + "\n" for r in rows)


def to_tsv(doc: Document) -> str:
    """One row per (individual, term): individual_id, role, kind, id, label, excluded."""
    header = ["individual_id", "role", "kind", "id", "label", "excluded"]
    rows = ["\t".join(header)]
    for pp in doc.phenopackets():
        sid = pp.subject.id
        any_term = False
        for ref in pp.term_refs():
            any_term = True
            rows.append("\t".join([sid, pp.role, ref.kind, ref.id, ref.label, "true" if ref.excluded else "false"]))
        if not any_term:
            rows.append("\t".join([sid, pp.role, "", "", "", ""]))
    return "\n".join(rows) + "\n"

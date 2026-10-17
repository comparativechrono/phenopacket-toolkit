"""Serialise Documents back out (strict / configurable writer)."""
from __future__ import annotations

import copy
import json
from typing import List, Optional

from ..model.document import Document
from ..model.profile import Dialect
from ..model.refs import iter_term_refs
from .dialects import get_adapter


def _resolve_dialect(doc: Document, dialect: str) -> str:
    if dialect == Dialect.PRESERVE:
        return doc.source.dialect
    return dialect


def to_json_str(doc: Document, *, dialect: str = Dialect.GA4GH,
                indent: int = 2) -> str:
    dial = _resolve_dialect(doc, dialect)
    data = copy.deepcopy(doc.raw)
    get_adapter(dial).from_canonical(data)
    # never leak internal bookkeeping keys
    _strip_internal(data)
    return json.dumps(data, indent=indent, ensure_ascii=False)


def _strip_internal(obj) -> None:
    if isinstance(obj, dict):
        obj.pop("_ppktk_inherited_metadata", None)
        for v in obj.values():
            _strip_internal(v)
    elif isinstance(obj, list):
        for v in obj:
            _strip_internal(v)


def write(doc: Document, path: str, *, dialect: str = Dialect.GA4GH,
          fmt: str = "json", indent: int = 2) -> None:
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError(
                "YAML support needs: pip install 'phenopacket-toolkit[yaml]'")
        dial = _resolve_dialect(doc, dialect)
        data = copy.deepcopy(doc.raw)
        get_adapter(dial).from_canonical(data)
        _strip_internal(data)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    else:
        text = to_json_str(doc, dialect=dialect, indent=indent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def write_many(docs: List[Document], path: str, *,
               dialect: str = Dialect.GA4GH) -> None:
    """Write newline-delimited JSON (one compact Document per line)."""
    with open(path, "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(to_json_str(d, dialect=dialect, indent=None))
            fh.write("\n")


# -- derived tabular exports ----------------------------------------------
_SEX_TO_PED = {"MALE": "1", "FEMALE": "2"}
_AFF_TO_PED = {"AFFECTED": "2", "UNAFFECTED": "1"}


def to_ped(doc: Document) -> str:
    """Emit a 6-column PED file from the pedigree."""
    ped = doc.pedigree()
    if ped is None:
        return ""
    rows = []
    fam = doc.id or "FAM"
    for person in ped.persons:
        rows.append("\t".join([
            person.raw.get("familyId", fam),
            person.individual_id,
            person.paternal_id or "0",
            person.maternal_id or "0",
            _SEX_TO_PED.get(person.sex, "0"),
            _AFF_TO_PED.get(person.affected_status, "0"),
        ]))
    return "\n".join(rows) + ("\n" if rows else "")


def to_tsv(doc: Document) -> str:
    """One row per (individual, term): individual_id, role, kind, curie, label, excluded."""
    header = ["individual_id", "role", "kind", "id", "label", "excluded"]
    rows = ["\t".join(header)]
    for pp in doc.phenopackets():
        sid = pp.subject.id
        any_term = False
        for ref in pp.term_refs():
            any_term = True
            rows.append("\t".join([
                sid, pp.role, ref.kind, ref.id, ref.label,
                "true" if ref.excluded else "false",
            ]))
        if not any_term:
            rows.append("\t".join([sid, pp.role, "", "", "", ""]))
    return "\n".join(rows) + "\n"

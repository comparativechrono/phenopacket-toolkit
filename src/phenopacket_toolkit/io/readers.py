"""Read GA4GH files into Documents.

There is one form of each file: the Phenopacket schema v2 JSON, and the GA4GH
Pedigree in its Phenopackets form, as written by pedigree-ga4gh. Proto field
names (``vital_status``) are read as their JSON names (``vitalStatus``), as
every proto3 JSON reader does. Files written by older versions of our own tools
(studio2ga4gh 0.3, abusua2ga4gh 0.2) are refused with an explanation: upgrade
them first with ``phenotk upgrade`` (or read them with ``allow_legacy=True``,
which only the upgrade command uses).
"""
from __future__ import annotations

from typing import List, Optional

from pedigree_ga4gh import detect, identify_legacy
from pedigree_ga4gh.io import loads as _loads
from pedigree_ga4gh.schema import camelise

from ..model.document import Document
from ..model.profile import SourceProfile

_MESSAGE = {"pedigree": "GA4GHPedigree", "family": "Family", "cohort": "Cohort", "phenopacket": "Phenopacket"}


class LegacyFileError(ValueError):
    """The file is one of the older, non-standard forms; run ``phenotk upgrade`` on it."""


def detect_format(path: str) -> str:
    p = path.lower()
    if p.endswith(".jsonl") or p.endswith(".ndjson"):
        return "jsonl"
    if p.endswith(".yaml") or p.endswith(".yml"):
        return "yaml"
    return "json"


def from_dict(data: dict, *, fmt: str = "json", path: str = "", allow_legacy: bool = False) -> Document:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object at the top level, got {}".format(type(data).__name__))
    old = identify_legacy(data)
    if old is not None and not old.upgradable:
        raise LegacyFileError("{}{}".format((path + ": ") if path else "", old.description))
    if old is not None and not allow_legacy:
        raise LegacyFileError("{}{} Run `phenotk upgrade {}` to convert it first.".format(
            (path + ": ") if path else "", old.description, path or "FILE"))
    profile = SourceProfile(fmt=fmt, path=path)
    kind = detect(data)
    if kind in _MESSAGE and old is None:
        renamed: List[str] = []
        data = camelise(data, _MESSAGE[kind], "", renamed)
        if renamed:
            profile.note("read {} proto field name(s) as JSON names (e.g. {})".format(len(renamed), renamed[0]))
    return Document(data, profile)


def loads(text: str, *, fmt: str = "json", path: str = "", allow_legacy: bool = False) -> Document:
    """Parse JSON (or YAML) text into a Document."""
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("YAML needs PyYAML: pip install 'phenopacket-toolkit[yaml]'")
        data = yaml.safe_load(text)
    else:
        data = _loads(text)
    return from_dict(data, fmt=fmt, path=path, allow_legacy=allow_legacy)


def read(path: str, *, fmt: Optional[str] = None, allow_legacy: bool = False) -> Document:
    """Read one document from a .json or .yaml file."""
    fmt = fmt or detect_format(path)
    if fmt == "jsonl":
        raise ValueError("use read_many() for .jsonl files")
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    return loads(text, fmt=fmt, path=path, allow_legacy=allow_legacy)


def read_many(path: str) -> List[Document]:
    """Read newline-delimited JSON: one Document per non-empty line."""
    docs: List[Document] = []
    with open(path, "r", encoding="utf-8-sig") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                docs.append(loads(line, fmt="json", path="{}:{}".format(path, n)))
    return docs

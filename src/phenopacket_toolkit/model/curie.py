"""Helpers for ontology-class dictionaries ({"id": ..., "label": ...}) and CURIEs."""
from __future__ import annotations

import re
from typing import Optional

# A CURIE is PREFIX:LOCAL, e.g. HP:0001626, MONDO:0011382.
_CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:[A-Za-z0-9_]+$")


def is_curie(value: Optional[str]) -> bool:
    return bool(value) and bool(_CURIE_RE.match(value))


def curie_prefix(curie: str) -> Optional[str]:
    if not curie or ":" not in curie:
        return None
    return curie.split(":", 1)[0]


def normalise_prefix(curie: str) -> str:
    """Upper-case the common biomedical prefixes (HP, MONDO, ...), keep the local id."""
    if not curie or ":" not in curie:
        return curie
    prefix, local = curie.split(":", 1)
    known = {"hp": "HP", "mondo": "MONDO", "omim": "OMIM", "ncit": "NCIT",
             "uberon": "UBERON", "hgnc": "HGNC", "so": "SO", "geno": "GENO",
             "efo": "EFO", "orpha": "ORPHA", "snomedct": "SNOMEDCT"}
    return "{}:{}".format(known.get(prefix.lower(), prefix), local)


def term_is_empty(term: Optional[dict]) -> bool:
    """A term with no id (un-normalised free text) or no content at all."""
    if not term:
        return True
    return not (term.get("id") or "").strip()

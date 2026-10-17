"""Locator objects for ontology terms, mirroring hponorm/mondonorm refs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass
class TermRef:
    """A reference to one ontology-class dict living inside a phenopacket.

    ``container`` is the parent dict that holds the term under ``key``
    (``"type"`` for a phenotypic feature, ``"term"`` for a disease), so callers
    can read *and* write the term in place.
    """

    path: str
    kind: str           # "phenotype" | "disease"
    container: dict     # the PhenotypicFeature or Disease dict
    key: str            # "type" or "term"

    @property
    def term(self) -> dict:
        return self.container.setdefault(self.key, {})

    @property
    def id(self) -> str:
        return (self.term.get("id") or "")

    @property
    def label(self) -> str:
        return (self.term.get("label") or "")

    @property
    def excluded(self) -> bool:
        return bool(self.container.get("excluded", False))

    def set(self, id_: str, label: str) -> None:
        t = self.term
        t["id"] = id_
        t["label"] = label


def iter_term_refs(packet: dict, base: str = "") -> Iterator[TermRef]:
    """Yield every phenotype and disease term inside one phenopacket dict."""
    prefix = (base + ".") if base else ""
    for i, feat in enumerate(packet.get("phenotypicFeatures", []) or []):
        if isinstance(feat, dict):
            yield TermRef("{}phenotypicFeatures[{}].type".format(prefix, i),
                          "phenotype", feat, "type")
    for i, dis in enumerate(packet.get("diseases", []) or []):
        if isinstance(dis, dict):
            yield TermRef("{}diseases[{}].term".format(prefix, i),
                          "disease", dis, "term")

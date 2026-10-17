"""Normalisation: fill term ids (mapping / hponorm / mondonorm) and tidy structure."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..model.curie import is_curie, normalise_prefix, term_is_empty
from ..model.document import Document
from ..ontology.policy import AutoAcceptPolicy


@dataclass
class DecisionLog:
    resolved: Dict[str, str] = field(default_factory=dict)     # label -> id
    unresolved: List[str] = field(default_factory=list)        # labels left empty
    notes: List[str] = field(default_factory=list)             # what happened / why

    def to_dict(self) -> dict:
        return {"resolved": self.resolved,
                "unresolved": sorted(set(self.unresolved)),
                "notes": self.notes}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def summary(self, *, to_stdout: bool = False) -> str:
        filled, empty = len(self.resolved), len(set(self.unresolved))
        lines = ["normalise: {} term(s) filled, {} left empty".format(filled, empty)]
        for n in self.notes:
            lines.append("  note: " + n)
        if self.unresolved:
            lines.append("  unresolved: " + ", ".join(sorted(set(self.unresolved))))
        if to_stdout:
            lines.append("  (normalised JSON written to stdout; "
                         "use -o FILE or --in-place to save it)")
        return "\n".join(lines)


def normalise(
    doc: Document,
    *,
    terms: bool = True,
    structure: bool = True,
    threshold: float = 0.9,
    backend: str = "auto",
    mapping: Optional[Dict[str, str]] = None,
    hpo_file: Optional[str] = None,
    mondo_file: Optional[str] = None,
    use_ontology: bool = True,
) -> Tuple[Document, DecisionLog]:
    """Return (new Document, decision log).

    Term filling order: an explicit ``mapping`` (label->id) always wins; any
    remaining empty terms are resolved via hponorm/mondonorm if ``use_ontology``
    and the packages are installed; otherwise they are left empty (no-guess).
    """
    out = doc.copy()
    log = DecisionLog()

    if terms:
        _fill_terms(out, mapping or {}, threshold, backend,
                    hpo_file, mondo_file, use_ontology, log)
    if structure:
        _normalise_structure(out)
    return out, log


def _fill_terms(doc, mapping, threshold, backend, hpo_file, mondo_file,
                use_ontology, log: DecisionLog) -> None:
    policy = AutoAcceptPolicy(threshold=threshold)
    lower_map = {k.lower(): v for k, v in mapping.items()}

    # backend handles: None = not yet attempted, False = attempted & unavailable,
    # otherwise a usable backend object. Built once, on first need.
    handles = {"phenotype": None, "disease": None}

    def get_backend(kind):
        if handles[kind] is None:
            try:
                if kind == "phenotype":
                    from ..ontology.backends import hpo_backend
                    handles[kind] = hpo_backend(backend=backend, hpo_file=hpo_file)
                    log.notes.append("phenotype backend ready ({} via hponorm)".format(backend))
                else:
                    from ..ontology.backends import mondo_backend
                    handles[kind] = mondo_backend(backend=backend, mondo_file=mondo_file)
                    log.notes.append("disease backend ready ({} via mondonorm)".format(backend))
            except RuntimeError as exc:
                handles[kind] = False
                log.notes.append(str(exc))   # actionable: explains the backend is missing
            except Exception as exc:          # noqa: BLE001 - never crash normalise on backend setup
                handles[kind] = False
                log.notes.append("{} backend unavailable: {}".format(kind, exc))
        return handles[kind]

    if not use_ontology:
        log.notes.append("ontology lookup disabled (--no-online): mapping-only")

    for pp in doc.phenopackets():
        for ref in pp.term_refs():
            if not term_is_empty(ref.term):
                if ref.id and ref.id != normalise_prefix(ref.id):
                    ref.set(normalise_prefix(ref.id), ref.label)
                continue
            label = ref.label.strip()
            if not label:
                continue

            # 1) explicit mapping wins
            hit = mapping.get(label) or lower_map.get(label.lower())
            if hit:
                ref.set(normalise_prefix(hit), ref.label)
                log.resolved[label] = ref.id
                continue

            # 2) ontology suggestion (only if enabled AND its backend is available)
            if use_ontology:
                be = get_backend(ref.kind)
                if be:
                    try:
                        cands = be.suggest(label)
                    except Exception as exc:                 # noqa: BLE001
                        cands = []
                        log.notes.append("suggest failed for {!r}: {}".format(label, exc))
                    chosen = policy.choose(cands)
                    if chosen:
                        ref.set(normalise_prefix(chosen.id), chosen.label or ref.label)
                        log.resolved[label] = ref.id
                        continue

            # 3) no-guess: leave empty
            log.unresolved.append(label)


def _normalise_structure(doc: Document) -> None:
    # canonicalise CURIE prefixes + dedupe terms within each packet
    for pp in doc.phenopackets():
        _dedupe(pp.raw, "phenotypicFeatures", "type")
        _dedupe(pp.raw, "diseases", "term")
    _rebuild_resources(doc)


def _dedupe(packet: dict, list_key: str, term_key: str) -> None:
    items = packet.get(list_key)
    if not items:
        return
    seen = set()
    out = []
    for item in items:
        term = item.get(term_key, {}) if isinstance(item, dict) else {}
        if term.get("id"):
            term["id"] = normalise_prefix(term["id"])
        key = (term.get("id", ""), term.get("label", ""), bool(item.get("excluded")))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    packet[list_key] = out


_RESOURCE_DEFS = {
    "HP": {"id": "hp", "name": "Human Phenotype Ontology",
           "url": "http://purl.obolibrary.org/obo/hp.owl",
           "namespacePrefix": "HP", "iriPrefix": "http://purl.obolibrary.org/obo/HP_"},
    "MONDO": {"id": "mondo", "name": "Mondo Disease Ontology",
              "url": "http://purl.obolibrary.org/obo/mondo.owl",
              "namespacePrefix": "MONDO", "iriPrefix": "http://purl.obolibrary.org/obo/MONDO_"},
    "GENO": {"id": "geno", "name": "Genotype Ontology",
             "url": "http://purl.obolibrary.org/obo/geno.owl",
             "namespacePrefix": "GENO", "iriPrefix": "http://purl.obolibrary.org/obo/GENO_"},
    "NCIT": {"id": "ncit", "name": "NCI Thesaurus",
             "url": "http://purl.obolibrary.org/obo/ncit.owl",
             "namespacePrefix": "NCIT", "iriPrefix": "http://purl.obolibrary.org/obo/NCIT_"},
    "UBERON": {"id": "uberon", "name": "Uberon multi-species anatomy ontology",
               "url": "http://purl.obolibrary.org/obo/uberon.owl",
               "namespacePrefix": "UBERON", "iriPrefix": "http://purl.obolibrary.org/obo/UBERON_"},
    "HGNC": {"id": "hgnc", "name": "HUGO Gene Nomenclature Committee",
             "url": "https://www.genenames.org",
             "namespacePrefix": "HGNC", "iriPrefix": "https://identifiers.org/hgnc/"},
    "LOINC": {"id": "loinc", "name": "Logical Observation Identifiers Names and Codes",
              "url": "https://loinc.org",
              "namespacePrefix": "LOINC", "iriPrefix": "https://loinc.org/"},
}


def _rebuild_resources(doc: Document) -> None:
    """Ensure metaData.resources lists every ontology actually used."""
    used = set()
    for pp in doc.phenopackets():
        for ref in pp.term_refs():
            if is_curie(ref.id):
                used.add(ref.id.split(":", 1)[0])

    md = doc.raw.setdefault("metaData", {})
    existing = {r.get("namespacePrefix"): r for r in md.get("resources", []) or []}
    for prefix in sorted(used):
        if prefix not in existing and prefix in _RESOURCE_DEFS:
            existing[prefix] = copy.deepcopy(_RESOURCE_DEFS[prefix])
    md["resources"] = [existing[k] for k in sorted(existing) if k]

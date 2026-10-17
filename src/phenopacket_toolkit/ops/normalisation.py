"""Normalisation: fill empty term ids (mapping, hponorm, mondonorm) and tidy the structure.

Term filling never guesses. An explicit ``mapping`` (label -> CURIE) always wins;
the remaining empty terms are looked up with hponorm (phenotypes) and mondonorm
(diseases) when they are installed, and filled only when the best match clears
``threshold``; anything else is left empty and listed in the decision log.

Tidying (``structure``) runs pedigree-ga4gh's upgrade on the document, which
puts CURIE prefixes in their usual case, checks KIN labels, and rebuilds each
metaData so it declares every ontology used, with all six resource fields. The
releases of the ontologies used to fill terms are recorded as the resource
versions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pedigree_ga4gh import upgrade as _upgrade
from pedigree_ga4gh.ontology import is_curie, prefix_of, tidy_curie

from ..model.curie import term_is_empty
from ..model.document import Document
from ..ontology.policy import AutoAcceptPolicy


@dataclass
class DecisionLog:
    resolved: Dict[str, str] = field(default_factory=dict)     # label -> id
    unresolved: List[str] = field(default_factory=list)        # labels left empty
    notes: List[str] = field(default_factory=list)             # what happened and why
    versions: Dict[str, str] = field(default_factory=dict)     # ontology prefix -> release used

    def to_dict(self) -> dict:
        return {"resolved": self.resolved, "unresolved": sorted(set(self.unresolved)),
                "notes": self.notes, "versions": self.versions}

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
            lines.append("  (normalised JSON written to stdout; use -o FILE or --in-place to save it)")
        return "\n".join(lines)


def _mapping_value(value) -> Tuple[str, str]:
    """A mapping entry as (curie, label); label is '' to keep the file's own label."""
    if isinstance(value, dict):
        return tidy_curie(value.get("id") or value.get("curie") or ""), (value.get("label") or "")
    return tidy_curie(str(value or "")), ""


def normalise(doc: Document, *, terms: bool = True, structure: bool = True, threshold: float = 0.9,
              backend: str = "auto", mapping: Optional[Dict] = None, hpo_file: Optional[str] = None,
              mondo_file: Optional[str] = None, use_ontology: bool = True,
              versions: Optional[Dict[str, str]] = None) -> Tuple[Document, DecisionLog]:
    """Return (new Document, decision log)."""
    out = doc.copy()
    log = DecisionLog()
    if versions:
        log.versions.update(versions)
    if terms:
        _fill_terms(out, mapping or {}, threshold, backend, hpo_file, mondo_file, use_ontology, log)
    if structure:
        _place_terms(out, log)
        _dedupe_terms(out)
        data, changes, _todo = _upgrade(out.raw, created_by="phenotk normalise", versions=log.versions)
        out.raw = data
        log.notes.extend(changes)
    return out, log


def _fill_terms(doc, mapping, threshold, backend, hpo_file, mondo_file, use_ontology, log: DecisionLog) -> None:
    policy = AutoAcceptPolicy(threshold=threshold)
    lower_map = {k.lower(): v for k, v in mapping.items()}
    handles = {"phenotype": None, "disease": None}

    def get_backend(kind):
        if handles[kind] is None:
            try:
                if kind == "phenotype":
                    from ..ontology.backends import hpo_backend
                    handles[kind] = hpo_backend(backend=backend, hpo_file=hpo_file)
                else:
                    from ..ontology.backends import mondo_backend
                    handles[kind] = mondo_backend(backend=backend, mondo_file=mondo_file)
                be = handles[kind]
                log.notes.append("{} terms looked up with {} ({})".format(
                    kind, "hponorm" if kind == "phenotype" else "mondonorm", be.name))
                if be.version:
                    log.versions.setdefault("HP" if kind == "phenotype" else "MONDO", be.version)
            except RuntimeError as exc:
                handles[kind] = False
                log.notes.append(str(exc))
            except Exception as exc:  # noqa: BLE001 - never crash normalise on backend set-up
                handles[kind] = False
                log.notes.append("{} look-up unavailable: {}".format(kind, exc))
        return handles[kind]

    if not use_ontology:
        log.notes.append("ontology look-up switched off: mapping only")

    for pp in doc.phenopackets():
        for ref in pp.term_refs():
            if not term_is_empty(ref.term):
                if ref.id != tidy_curie(ref.id):
                    ref.set(tidy_curie(ref.id), ref.label)
                continue
            label = ref.label.strip()
            if not label:
                continue
            hit = mapping.get(label) if label in mapping else lower_map.get(label.lower())
            if hit:
                curie, new_label = _mapping_value(hit)
                if is_curie(curie):
                    ref.set(curie, new_label or ref.label)
                    log.resolved[label] = curie
                    # a terms file records the release each term came from (Match conditions to terms writes it)
                    if isinstance(hit, dict) and hit.get("version"):
                        log.versions.setdefault(prefix_of(curie), str(hit["version"]))
                    continue
                log.notes.append("mapping for {!r} is not a CURIE: {!r}".format(label, curie))
            if use_ontology:
                be = get_backend(ref.kind)
                if be:
                    try:
                        cands = be.suggest(label)
                    except Exception as exc:  # noqa: BLE001
                        cands = []
                        log.notes.append("look-up failed for {!r}: {}".format(label, exc))
                    if not cands and getattr(be, "last_error", None):
                        log.notes.append("look-up for {!r} got no answer: {}".format(label, be.last_error))
                    chosen = policy.choose(cands)
                    if chosen:
                        ref.set(tidy_curie(chosen.id), chosen.label or ref.label)
                        log.resolved[label] = ref.id
                        continue
            log.unresolved.append(label)
    for prefix in {prefix_of(v) for v in log.resolved.values()}:
        log.versions.setdefault(prefix, "")
    log.versions = {k: v for k, v in log.versions.items() if v}


# A disease is named by a disease ontology and a phenotypic feature by a phenotype ontology (Phenopackets v2:
# Disease.term "e.g. MONDO, OMIM, Orphanet, DOID"; PhenotypicFeature.type "HPO recommended"). A name that is
# filled in with a term of the other kind – "Hearing loss from birth", written as a disease by an older tool, is
# HP:0000365 – is moved to where its term belongs, with the fields both have.
_DISEASE_PREFIXES = {"MONDO", "OMIM", "ORPHA", "Orphanet", "DOID"}
_SHARED = ("excluded", "onset", "resolution")


def _place_terms(doc: Document, log: DecisionLog) -> None:
    for pp in doc.phenopackets():
        raw = pp.raw
        diseases, features = raw.get("diseases") or [], raw.get("phenotypicFeatures") or []
        to_features = [d for d in diseases if isinstance(d, dict) and prefix_of((d.get("term") or {}).get("id", "")) == "HP"
                       and set(d) <= {"term", *_SHARED}]
        to_diseases = [f for f in features if isinstance(f, dict)
                       and prefix_of((f.get("type") or {}).get("id", "")) in _DISEASE_PREFIXES
                       and set(f) <= {"type", *_SHARED}]
        if not to_features and not to_diseases:
            continue
        who = pp.subject.id or pp.path or "?"
        for d in to_features:
            feature = {"type": d["term"]}
            feature.update({k: d[k] for k in _SHARED if k in d})
            features.append(feature)
            log.notes.append("{}: {} '{}' is a phenotype (HPO), so it moved from diseases to phenotypicFeatures".format(
                who, d["term"].get("id"), d["term"].get("label", "")))
        for f in to_diseases:
            disease = {"term": f["type"]}
            disease.update({k: f[k] for k in _SHARED if k in f})
            diseases.append(disease)
            log.notes.append("{}: {} '{}' is a disease, so it moved from phenotypicFeatures to diseases".format(
                who, f["type"].get("id"), f["type"].get("label", "")))
        diseases = [d for d in diseases if not any(d is x for x in to_features)]
        features = [f for f in features if not any(f is x for x in to_diseases)]
        for key, items in (("diseases", diseases), ("phenotypicFeatures", features)):
            if items:
                raw[key] = items
            else:
                raw.pop(key, None)


def _dedupe_terms(doc: Document) -> None:
    for pp in doc.phenopackets():
        for list_key, term_key in (("phenotypicFeatures", "type"), ("diseases", "term")):
            items = pp.raw.get(list_key)
            if not items:
                continue
            seen, kept = set(), []
            for item in items:
                term = item.get(term_key, {}) if isinstance(item, dict) else {}
                key = (term.get("id", ""), term.get("label", ""), bool(item.get("excluded")))
                if term.get("id") and key in seen:
                    continue
                seen.add(key)
                kept.append(item)
            pp.raw[list_key] = kept

"""Summary statistics over a Document (the flagstat equivalent)."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..model.curie import term_is_empty
from ..model.document import Document


@dataclass
class StatsResult:
    n_individuals: int = 0
    by_sex: Dict[str, int] = field(default_factory=dict)
    by_affected: Dict[str, int] = field(default_factory=dict)
    n_phenotypes: int = 0
    n_diseases: int = 0
    n_excluded: int = 0
    n_unnormalised: int = 0
    term_counts: Counter = field(default_factory=Counter)
    relationships: Counter = field(default_factory=Counter)

    def term_frequency(self, top: int = 10) -> List[Tuple[str, int]]:
        return self.term_counts.most_common(top)

    def to_dict(self) -> dict:
        return {
            "individuals": self.n_individuals,
            "by_sex": dict(self.by_sex),
            "by_affected_status": dict(self.by_affected),
            "phenotypic_features": self.n_phenotypes,
            "diseases": self.n_diseases,
            "excluded_features": self.n_excluded,
            "unnormalised_terms": self.n_unnormalised,
            "top_terms": self.term_frequency(),
            "relationships": dict(self.relationships),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def stats(doc: Document) -> StatsResult:
    res = StatsResult()
    sex_c, aff_c = Counter(), Counter()

    ped = doc.pedigree()
    if ped is not None:
        for p in ped.persons:
            sex_c[p.sex] += 1
            aff_c[p.affected_status] += 1
        res.n_individuals = len(ped.persons)
    else:
        aff = doc.affected_status()
        for pp in doc.phenopackets():
            sex_c[pp.subject.sex or "UNKNOWN_SEX"] += 1
            aff_c[aff.get(pp.subject.id, "MISSING")] += 1
    for r in doc.relationships():
        res.relationships[r.relation_label or r.relation_id] += 1

    seen_subjects = 0
    for pp in doc.phenopackets():
        seen_subjects += 1
        for ref in pp.term_refs():
            if ref.kind == "phenotype":
                res.n_phenotypes += 1
                if ref.excluded:
                    res.n_excluded += 1
            else:
                res.n_diseases += 1
            if term_is_empty(ref.term):
                res.n_unnormalised += 1
            key = ref.id or ("label:" + ref.label if ref.label else "<empty>")
            res.term_counts[key] += 1

    if res.n_individuals == 0:
        res.n_individuals = seen_subjects
    res.by_sex = dict(sex_c)
    res.by_affected = dict(aff_c)
    return res


def render_stats(res: StatsResult, *, fmt: str = "human") -> str:
    if fmt == "json":
        return res.to_json()
    lines = [
        "individuals:        {}".format(res.n_individuals),
        "  by sex:           {}".format(_kv(res.by_sex)),
        "  by affected:      {}".format(_kv(res.by_affected)),
        "phenotypic features: {} ({} excluded)".format(res.n_phenotypes, res.n_excluded),
        "diseases:           {}".format(res.n_diseases),
        "unnormalised terms: {}".format(res.n_unnormalised),
    ]
    if res.relationships:
        lines.append("relationships:")
        for label, n in res.relationships.most_common():
            lines.append("  {:>3}  {}".format(n, label))
    top = res.term_frequency()
    if top:
        lines.append("top terms:")
        for term, n in top:
            lines.append("  {:>3}  {}".format(n, term))
    return "\n".join(lines)


def _kv(d: dict) -> str:
    return ", ".join("{}={}".format(k, v) for k, v in sorted(d.items())) or "-"

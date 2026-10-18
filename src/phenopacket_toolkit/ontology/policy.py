"""Auto-accept policy applied to ranked ontology suggestions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

#: The default threshold. hponorm and mondonorm score a name 100 when it is the term's label and 98 when it is one
#: of its synonyms, ignoring case and punctuation; rescaled to 0-1, only the term's own names reach 0.98. Anything
#: lower is a name that is merely alike, and names spelt alike can mean opposite things ("Maternal hypothyroidism",
#: "Maternal hyperthyroidism").
EXACT_MATCH = 0.98


@dataclass
class Candidate:
    id: str
    label: str
    score: float


@dataclass
class AutoAcceptPolicy:
    """Accept the top candidate iff its score clears the threshold.

    Mirrors the no-guess contract of hponorm/mondonorm: below the threshold we
    decline and leave the id empty rather than guess. The default accepts only
    the term's label or one of its synonyms; a lower threshold accepts close
    names as well, and each of those is a guess for a person to check.
    """

    threshold: float = EXACT_MATCH

    def choose(self, candidates: Sequence[Candidate]) -> Optional[Candidate]:
        if not candidates:
            return None
        top = candidates[0]
        if top.score >= self.threshold:
            return top
        return None

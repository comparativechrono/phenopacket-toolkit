"""Auto-accept policy applied to ranked ontology suggestions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class Candidate:
    id: str
    label: str
    score: float


@dataclass
class AutoAcceptPolicy:
    """Accept the top candidate iff its score clears the threshold.

    Mirrors the no-guess contract of hponorm/mondonorm: below the threshold we
    decline and leave the id empty rather than guess.
    """

    threshold: float = 0.9

    def choose(self, candidates: Sequence[Candidate]) -> Optional[Candidate]:
        if not candidates:
            return None
        top = candidates[0]
        if top.score >= self.threshold:
            return top
        return None

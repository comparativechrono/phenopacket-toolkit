"""Dialect identification and source provenance."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class Dialect:
    """Known structural dialects. Plain strings so third parties can add more."""

    GA4GH = "ga4gh"      # canonical, spec-compliant
    ABUSUA = "abusua"    # abusua2ga4gh *.family.json (snake_case vital_status, per-pp metaData)
    STUDIO = "studio"    # studio2ga4gh *_phenopackets.json (metaData only at top level)
    PRESERVE = "preserve"  # writer pseudo-dialect: re-emit in the source dialect

    ALL = (GA4GH, ABUSUA, STUDIO)


@dataclass
class SourceProfile:
    """What we read and what we changed to reach canonical form."""

    dialect: str = Dialect.GA4GH
    fmt: str = "json"            # json | jsonl | yaml
    path: str = ""
    adaptations: List[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.adaptations.append(msg)

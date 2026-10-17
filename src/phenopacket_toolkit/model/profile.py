"""Where a document came from."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SourceProfile:
    """What was read, and any proto field names that were put into JSON form on reading."""

    fmt: str = "json"            # json | jsonl | yaml
    path: str = ""
    adaptations: List[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.adaptations.append(msg)

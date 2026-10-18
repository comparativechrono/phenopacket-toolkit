"""Structured validation findings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class Severity:
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    _RANK = {ERROR: 3, WARNING: 2, INFO: 1}


@dataclass
class Finding:
    level: str        # "standard" for the checks of pedigree_ga4gh.validate
    severity: str     # Severity.*
    code: str         # short stable identifier, e.g. "missing-metadata"
    message: str
    path: str = ""    # locator within the document
    fix: str = ""     # human hint on how to resolve

    def to_dict(self) -> dict:
        return {"level": self.level, "severity": self.severity, "code": self.code,
                "message": self.message, "path": self.path, "fix": self.fix}


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "counts": {
                "error": len(self.errors),
                "warning": len(self.warnings),
                "info": len([f for f in self.findings if f.severity == Severity.INFO]),
            },
            "findings": [f.to_dict() for f in self.findings],
        }

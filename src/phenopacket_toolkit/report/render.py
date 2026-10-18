"""Renderers for reports and stats."""
from __future__ import annotations

import json

from .findings import Report, Severity

_SYMBOL = {Severity.ERROR: "E", Severity.WARNING: "W", Severity.INFO: "i"}


def render_report(report: Report, *, fmt: str = "human") -> str:
    if fmt == "json":
        return json.dumps(report.to_dict(), indent=2)
    if not report.findings:
        return "OK - no problems found."
    lines = []
    for f in report.findings:
        loc = " [{}]".format(f.path) if f.path else ""
        lines.append("{}  {:<10} {}{}".format(
            _SYMBOL.get(f.severity, "?"), f.code, f.message, loc))
        if f.fix:
            lines.append("        fix: {}".format(f.fix))
    d = report.to_dict()["counts"]
    lines.append("")
    lines.append("{} error(s), {} warning(s), {} info".format(
        d["error"], d["warning"], d["info"]))
    return "\n".join(lines)

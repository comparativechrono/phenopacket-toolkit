"""Shared helpers for dialect adapters."""
from __future__ import annotations

from typing import Iterator


def iter_packets(data: dict) -> Iterator[dict]:
    """Yield every embedded phenopacket dict in a Family/Cohort/Phenopacket."""
    if "proband" in data and isinstance(data["proband"], dict):
        yield data["proband"]
    for rel in data.get("relatives", []) or []:
        if isinstance(rel, dict):
            yield rel
    for m in data.get("members", []) or []:
        if isinstance(m, dict):
            yield m
    if "proband" not in data and "relatives" not in data and "members" not in data:
        # a bare phenopacket
        if "subject" in data or "phenotypicFeatures" in data or "diseases" in data:
            yield data

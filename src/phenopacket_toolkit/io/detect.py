"""Sniff serialization format and structural dialect."""
from __future__ import annotations

from ..model.profile import Dialect
from .dialects._common import iter_packets


def detect_format(path: str) -> str:
    p = path.lower()
    if p.endswith(".jsonl") or p.endswith(".ndjson"):
        return "jsonl"
    if p.endswith(".yaml") or p.endswith(".yml"):
        return "yaml"
    return "json"


def detect_dialect(data: dict) -> str:
    """Heuristic dialect detection from a parsed dict.

    abusua: any subject carries snake_case ``vital_status``.
    studio: it's a Family whose embedded phenopackets have no metaData.
    otherwise: canonical ga4gh.
    """
    packets = list(iter_packets(data))

    for pp in packets:
        subj = pp.get("subject")
        if isinstance(subj, dict) and "vital_status" in subj:
            return Dialect.ABUSUA

    is_family = "proband" in data or "relatives" in data
    if is_family and data.get("metaData"):
        embedded = [pp for pp in packets if pp is not data]
        if embedded and all(not pp.get("metaData") for pp in embedded):
            return Dialect.STUDIO

    return Dialect.GA4GH

"""abusua2ga4gh ``*.family.json`` dialect.

Quirks vs canonical:
  * subject uses ``vital_status`` (snake_case) instead of ``vitalStatus``.
Everything else (per-phenopacket metaData, consanguinousParents) is already
spec-shaped, so canonicalisation only fixes the casing.
"""
from __future__ import annotations

from ._common import iter_packets


def to_canonical(data: dict, profile=None) -> dict:
    changed = 0
    for pp in iter_packets(data):
        subj = pp.get("subject")
        if isinstance(subj, dict) and "vital_status" in subj and "vitalStatus" not in subj:
            subj["vitalStatus"] = subj.pop("vital_status")
            changed += 1
    if profile is not None and changed:
        profile.note("renamed vital_status -> vitalStatus on {} subject(s)".format(changed))
    return data


def from_canonical(data: dict) -> dict:
    for pp in iter_packets(data):
        subj = pp.get("subject")
        if isinstance(subj, dict) and "vitalStatus" in subj:
            subj["vital_status"] = subj.pop("vitalStatus")
    return data

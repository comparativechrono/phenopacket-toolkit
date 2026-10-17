"""studio2ga4gh ``*_phenopackets.json`` dialect.

Quirks vs canonical:
  * metaData lives only at the Family level; embedded phenopackets have none.
A standalone Phenopacket requires its own metaData, so on read we copy the
Family metaData into each embedded phenopacket that lacks one. On write we
strip those inherited blocks again so the file matches what studio2ga4gh emits.
"""
from __future__ import annotations

import copy

from ._common import iter_packets


def to_canonical(data: dict, profile=None) -> dict:
    family_md = data.get("metaData")
    if not family_md:
        return data
    inherited = 0
    for pp in iter_packets(data):
        if pp is data:           # bare phenopacket; nothing to inherit
            continue
        if not pp.get("metaData"):
            pp["metaData"] = copy.deepcopy(family_md)
            pp["_ppktk_inherited_metadata"] = True
            inherited += 1
    if profile is not None and inherited:
        profile.note("inherited Family metaData into {} phenopacket(s)".format(inherited))
    return data


def from_canonical(data: dict) -> dict:
    for pp in iter_packets(data):
        if pp.get("_ppktk_inherited_metadata"):
            pp.pop("metaData", None)
        pp.pop("_ppktk_inherited_metadata", None)
    return data

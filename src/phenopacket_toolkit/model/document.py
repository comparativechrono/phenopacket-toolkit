"""The Document: a parsed phenopacket artifact (Family, Phenopacket or Cohort)."""
from __future__ import annotations

import copy as _copy
from typing import Iterator, List, Optional

from .profile import Dialect, SourceProfile
from .views import PedigreeView, PhenopacketView


class Document:
    """Holds the canonicalised dict plus provenance.

    The dict is always in *canonical* (ga4gh) shape in memory; dialect handling
    happens only in the io layer. Unknown keys are preserved verbatim.
    """

    def __init__(self, data: dict, source: Optional[SourceProfile] = None):
        self.raw = data
        self.source = source or SourceProfile()

    # -- shape -------------------------------------------------------------
    @property
    def kind(self) -> str:
        if "proband" in self.raw or "relatives" in self.raw:
            return "family"
        if "members" in self.raw:
            return "cohort"
        return "phenopacket"

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    # -- iteration ---------------------------------------------------------
    def phenopackets(self) -> Iterator[PhenopacketView]:
        """Yield every contained phenopacket, regardless of top-level shape."""
        k = self.kind
        if k == "phenopacket":
            yield PhenopacketView(self.raw, role="proband")
        elif k == "family":
            if isinstance(self.raw.get("proband"), dict):
                yield PhenopacketView(self.raw["proband"], role="proband",
                                      path="proband")
            for i, rel in enumerate(self.raw.get("relatives", []) or []):
                if isinstance(rel, dict):
                    yield PhenopacketView(rel, role="relative",
                                          path="relatives[{}]".format(i))
        elif k == "cohort":
            for i, m in enumerate(self.raw.get("members", []) or []):
                if isinstance(m, dict):
                    yield PhenopacketView(m, role="relative",
                                          path="members[{}]".format(i))

    def proband(self) -> Optional[PhenopacketView]:
        for pp in self.phenopackets():
            if pp.role == "proband":
                return pp
        return None

    def pedigree(self) -> Optional[PedigreeView]:
        ped = self.raw.get("pedigree")
        return PedigreeView(ped) if ped else None

    @property
    def metadata(self) -> dict:
        return self.raw.get("metaData", {})

    # -- helpers -----------------------------------------------------------
    def copy(self) -> "Document":
        return Document(_copy.deepcopy(self.raw),
                        _copy.deepcopy(self.source))

    def to_dict(self) -> dict:
        return self.raw

    def __repr__(self) -> str:
        return "Document(kind={!r}, id={!r}, dialect={!r})".format(
            self.kind, self.id, self.source.dialect)

    # -- verb sugar (delegates to ops; imported lazily to avoid cycles) ----
    def validate(self, level: str = "lint"):
        from ..ops.validation import validate as _v
        return _v(self, level=level)

    def stats(self):
        from ..ops.statistics import stats as _s
        return _s(self)

    def filter(self, **opts) -> "Document":
        from ..ops.filter import filter_document as _f
        return _f(self, **opts)

    def deidentify(self, **opts) -> "Document":
        from ..ops.deidentification import deidentify as _d
        return _d(self, **opts)

    def normalise(self, **opts):
        from ..ops.normalisation import normalise as _n
        return _n(self, **opts)

    def sort(self) -> "Document":
        from ..ops.sort import sort_document as _so
        return _so(self)

    def add(self, target="proband", **opts) -> "Document":
        from ..ops.annotate import add as _a
        return _a(self, target, **opts)

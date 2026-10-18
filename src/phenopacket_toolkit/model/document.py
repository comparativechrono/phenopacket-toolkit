"""The Document: a parsed GA4GH file (Pedigree, Family, Phenopacket or Cohort)."""
from __future__ import annotations

import copy as _copy
from typing import Iterator, List, Optional

from .profile import SourceProfile
from .views import PedigreeView, PhenopacketView, RelationshipView

# The four kinds of document, as pedigree_ga4gh.detect names them.
KINDS = ("pedigree", "family", "phenopacket", "cohort")
KIND_NAMES = {"pedigree": "GA4GH Pedigree", "family": "Phenopackets Family",
              "phenopacket": "Phenopacket", "cohort": "Phenopackets Cohort"}


class Document:
    """The parsed JSON plus where it came from.

    The dict always uses the JSON (camelCase) field names; readers translate
    proto names on the way in. Unknown keys are kept as they are, so that
    validation can report them.
    """

    def __init__(self, data: dict, source: Optional[SourceProfile] = None):
        self.raw = data
        self.source = source or SourceProfile()

    # -- shape -------------------------------------------------------------
    @property
    def kind(self) -> str:
        from pedigree_ga4gh import detect
        k = detect(self.raw)
        return k if k in KINDS else "phenopacket"

    @property
    def kind_name(self) -> str:
        return KIND_NAMES[self.kind]

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    def index_patients(self) -> List[str]:
        return list(self.raw.get("indexPatients") or [])

    # -- iteration ---------------------------------------------------------
    def phenopackets(self) -> Iterator[PhenopacketView]:
        """Every Phenopacket in the document, whatever its kind."""
        k = self.kind
        if k == "phenopacket":
            yield PhenopacketView(self.raw, role="proband")
        elif k == "family":
            if isinstance(self.raw.get("proband"), dict):
                yield PhenopacketView(self.raw["proband"], role="proband", path="proband")
            for i, rel in enumerate(self.raw.get("relatives", []) or []):
                if isinstance(rel, dict):
                    yield PhenopacketView(rel, role="relative", path="relatives[{}]".format(i))
        elif k == "cohort":
            for i, m in enumerate(self.raw.get("members", []) or []):
                if isinstance(m, dict):
                    yield PhenopacketView(m, role="member", path="members[{}]".format(i))
        elif k == "pedigree":
            index = set(self.index_patients())
            for i, m in enumerate(self.raw.get("individuals", []) or []):
                if isinstance(m, dict):
                    sid = (m.get("subject") or {}).get("id")
                    yield PhenopacketView(m, role="proband" if sid in index else "relative",
                                          path="individuals[{}]".format(i))

    def proband(self) -> Optional[PhenopacketView]:
        for pp in self.phenopackets():
            if pp.role == "proband":
                return pp
        return None

    def pedigree(self) -> Optional[PedigreeView]:
        """The PED-style pedigree of a Family (``None`` for other kinds)."""
        ped = self.raw.get("pedigree") if self.kind == "family" else None
        return PedigreeView(ped) if ped else None

    def relationships(self) -> List[RelationshipView]:
        """The KIN relationships of a GA4GH Pedigree (empty for other kinds)."""
        if self.kind != "pedigree":
            return []
        return [RelationshipView(r) for r in self.raw.get("relationships") or [] if isinstance(r, dict)]

    def affected_status(self) -> dict:
        """subject id -> AFFECTED, UNAFFECTED or MISSING, for every kind of document."""
        ped = self.pedigree()
        if ped is not None:
            return {p.individual_id: p.affected_status for p in ped.persons}
        out = {}
        for pp in self.phenopackets():
            refs = list(pp.term_refs())
            if any(not r.excluded for r in refs):
                out[pp.subject.id] = "AFFECTED"
            elif refs:
                out[pp.subject.id] = "UNAFFECTED"
            else:
                out[pp.subject.id] = "MISSING"
        return out

    @property
    def metadata(self) -> dict:
        return self.raw.get("metaData", {})

    # -- helpers -----------------------------------------------------------
    def copy(self) -> "Document":
        return Document(_copy.deepcopy(self.raw), _copy.deepcopy(self.source))

    def to_dict(self) -> dict:
        return self.raw

    def __repr__(self) -> str:
        return "Document(kind={!r}, id={!r})".format(self.kind, self.id)

    # -- verb sugar (delegates to ops; imported lazily to avoid cycles) ----
    def validate(self):
        from ..ops.validation import validate as _v
        return _v(self)

    def stats(self):
        from ..ops.statistics import stats as _s
        return _s(self)

    def filter(self, **opts) -> "Document":
        from ..ops.filter import filter_document as _f
        return _f(self, **opts)

    def deidentify(self, **opts):
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

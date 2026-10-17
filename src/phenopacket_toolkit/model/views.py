"""Lightweight typed facades over the canonical dicts.

Views never copy: they read and write through to the underlying dict, so edits
made via a view are visible on the owning Document.
"""
from __future__ import annotations

from typing import Iterator, List, Optional

from .refs import TermRef, iter_term_refs


class IndividualView:
    def __init__(self, data: dict):
        self._d = data

    @property
    def id(self) -> str:
        return self._d.get("id", "")

    @property
    def sex(self) -> Optional[str]:
        return self._d.get("sex")

    @property
    def date_of_birth(self) -> Optional[str]:
        return self._d.get("dateOfBirth")

    @property
    def vital_status(self) -> Optional[dict]:
        return self._d.get("vitalStatus")

    @property
    def raw(self) -> dict:
        return self._d


class PhenopacketView:
    def __init__(self, data: dict, role: str = "proband", path: str = ""):
        self._d = data
        self.role = role            # "proband" | "relative" | "member"
        self.path = path

    @property
    def id(self) -> str:
        return self._d.get("id", "")

    @property
    def subject(self) -> IndividualView:
        return IndividualView(self._d.setdefault("subject", {}))

    def term_refs(self) -> Iterator[TermRef]:
        return iter_term_refs(self._d, self.path)

    @property
    def has_metadata(self) -> bool:
        return bool(self._d.get("metaData"))

    @property
    def raw(self) -> dict:
        return self._d


class Person:
    """One row of a Pedigree (PED-compatible)."""

    def __init__(self, data: dict):
        self._d = data

    @property
    def individual_id(self) -> str:
        return self._d.get("individualId", "")

    @property
    def paternal_id(self) -> str:
        return self._d.get("paternalId", "0")

    @property
    def maternal_id(self) -> str:
        return self._d.get("maternalId", "0")

    @property
    def sex(self) -> str:
        return self._d.get("sex", "UNKNOWN_SEX")

    @property
    def affected_status(self) -> str:
        return self._d.get("affectedStatus", "MISSING")

    @property
    def raw(self) -> dict:
        return self._d


class RelationshipView:
    """One relationship of a GA4GH Pedigree: individual *relation* relative."""

    def __init__(self, data: dict):
        self._d = data

    @property
    def individual(self) -> str:
        return self._d.get("individualId", "")

    @property
    def relative(self) -> str:
        return self._d.get("relativeId", "")

    @property
    def relation_id(self) -> str:
        return (self._d.get("relation") or {}).get("id", "")

    @property
    def relation_label(self) -> str:
        return (self._d.get("relation") or {}).get("label", "")

    @property
    def raw(self) -> dict:
        return self._d


class PedigreeView:
    def __init__(self, data: dict):
        self._d = data or {}

    @property
    def persons(self) -> List[Person]:
        return [Person(p) for p in self._d.get("persons", []) or []]

    @property
    def raw(self) -> dict:
        return self._d

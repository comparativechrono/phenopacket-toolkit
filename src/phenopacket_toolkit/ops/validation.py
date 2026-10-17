"""Layered validation: structural, reference/graph, ontology, lint."""
from __future__ import annotations

from typing import List

from ..model.curie import is_curie, normalise_prefix, term_is_empty
from ..model.document import Document
from ..report.findings import Report, Severity

_LEVELS = ["syntactic", "structural", "reference", "ontology", "lint"]
_VALID_SEX = {"MALE", "FEMALE", "OTHER_SEX", "UNKNOWN_SEX"}
_VALID_AFF = {"AFFECTED", "UNAFFECTED", "MISSING"}


def _levels_through(level: str) -> List[str]:
    if level not in _LEVELS:
        raise ValueError("unknown level {!r}; choose from {}".format(level, _LEVELS))
    return _LEVELS[: _LEVELS.index(level) + 1]


def validate(doc: Document, *, level: str = "lint", online: bool = False) -> Report:
    rep = Report()
    levels = _levels_through(level)

    if "structural" in levels:
        _check_structural(doc, rep)
    if "reference" in levels:
        _check_reference(doc, rep)
    if "ontology" in levels:
        _check_ontology(doc, rep, online=online)
    if "lint" in levels:
        _check_lint(doc, rep)
    return rep


def _check_structural(doc: Document, rep: Report) -> None:
    if not doc.id:
        rep.add("structural", Severity.WARNING, "missing-id",
                "top-level object has no id", path="")
    saw_packet = False
    for pp in doc.phenopackets():
        saw_packet = True
        if not pp.subject.id:
            rep.add("structural", Severity.ERROR, "missing-subject-id",
                    "phenopacket has no subject.id", path=pp.path)
        if not pp.has_metadata:
            rep.add("structural", Severity.WARNING, "missing-metadata",
                    "phenopacket has no metaData (required for a standalone Phenopacket)",
                    path=pp.path,
                    fix="run `phenotk normalise --structure` to synthesise one")
    if not saw_packet:
        rep.add("structural", Severity.ERROR, "no-phenopackets",
                "no phenopackets found in document", path="")


def _check_reference(doc: Document, rep: Report) -> None:
    ped = doc.pedigree()
    subject_ids = {pp.subject.id for pp in doc.phenopackets() if pp.subject.id}

    if ped is None:
        if doc.kind == "family":
            rep.add("reference", Severity.WARNING, "no-pedigree",
                    "family has no pedigree", path="")
        return

    persons = ped.persons
    ped_ids = {p.individual_id for p in persons}

    # every subject must appear in the pedigree
    for sid in subject_ids:
        if sid not in ped_ids:
            rep.add("reference", Severity.ERROR, "subject-not-in-pedigree",
                    "subject id {!r} is not present in the pedigree".format(sid),
                    path="pedigree",
                    fix="pedigree individualId must match phenopacket subject.id")

    for i, p in enumerate(persons):
        loc = "pedigree.persons[{}]".format(i)
        if not p.individual_id:
            rep.add("reference", Severity.ERROR, "missing-individual-id",
                    "pedigree person has no individualId", path=loc)
        if p.sex not in _VALID_SEX:
            rep.add("reference", Severity.WARNING, "bad-sex",
                    "unexpected sex value {!r}".format(p.sex), path=loc)
        if p.affected_status not in _VALID_AFF:
            rep.add("reference", Severity.WARNING, "bad-affected-status",
                    "unexpected affectedStatus {!r}".format(p.affected_status), path=loc)
        for role, pid in (("paternalId", p.paternal_id), ("maternalId", p.maternal_id)):
            if pid and pid != "0" and pid not in ped_ids:
                rep.add("reference", Severity.ERROR, "dangling-parent",
                        "{} {!r} of {!r} is not in the pedigree".format(role, pid, p.individual_id),
                        path=loc)

    _check_sex_of_parents(persons, rep)
    _check_no_cycles(persons, rep)


def _check_sex_of_parents(persons, rep: Report) -> None:
    sex_by_id = {p.individual_id: p.sex for p in persons}
    for p in persons:
        if p.paternal_id and p.paternal_id != "0":
            s = sex_by_id.get(p.paternal_id)
            if s == "FEMALE":
                rep.add("reference", Severity.WARNING, "father-not-male",
                        "paternalId {!r} is recorded as FEMALE".format(p.paternal_id),
                        path="pedigree")
        if p.maternal_id and p.maternal_id != "0":
            s = sex_by_id.get(p.maternal_id)
            if s == "MALE":
                rep.add("reference", Severity.WARNING, "mother-not-female",
                        "maternalId {!r} is recorded as MALE".format(p.maternal_id),
                        path="pedigree")


def _check_no_cycles(persons, rep: Report) -> None:
    parents = {}
    for p in persons:
        ps = []
        for pid in (p.paternal_id, p.maternal_id):
            if pid and pid != "0":
                ps.append(pid)
        parents[p.individual_id] = ps

    WHITE, GREY, BLACK = 0, 1, 2
    color = {pid: WHITE for pid in parents}

    def visit(node, stack):
        color[node] = GREY
        for par in parents.get(node, []):
            if par not in color:
                continue
            if color[par] == GREY:
                rep.add("reference", Severity.ERROR, "pedigree-cycle",
                        "ancestry cycle involving {!r}".format(par), path="pedigree")
                return
            if color[par] == WHITE:
                visit(par, stack + [par])
        color[node] = BLACK

    for pid in list(parents):
        if color.get(pid, BLACK) == WHITE:
            visit(pid, [pid])


def _check_ontology(doc: Document, rep: Report, *, online: bool = False) -> None:
    declared = _declared_prefixes(doc)
    for pp in doc.phenopackets():
        for ref in pp.term_refs():
            cid = ref.id
            if not cid:
                continue  # empty id handled by lint (un-normalised)
            if not is_curie(cid):
                rep.add("ontology", Severity.ERROR, "bad-curie",
                        "term id {!r} is not a valid CURIE".format(cid),
                        path=ref.path)
                continue
            prefix = cid.split(":", 1)[0]
            if declared and prefix not in declared:
                rep.add("ontology", Severity.WARNING, "undeclared-resource",
                        "{} used but not declared in metaData.resources".format(prefix),
                        path=ref.path,
                        fix="run `phenotk normalise --structure` to rebuild resources")
    # online resolution intentionally omitted from the zero-dep core; the
    # [validate]/[normalise] extras add authoritative checks.


def _declared_prefixes(doc: Document) -> set:
    prefixes = set()
    for md in [doc.metadata] + [pp.raw.get("metaData", {}) for pp in doc.phenopackets()]:
        for res in (md or {}).get("resources", []) or []:
            ns = res.get("namespacePrefix") or res.get("namespace_prefix")
            if ns:
                prefixes.add(ns)
    return prefixes


def _check_lint(doc: Document, rep: Report) -> None:
    for pp in doc.phenopackets():
        subj = pp.subject.raw
        if "vital_status" in subj:
            rep.add("lint", Severity.INFO, "snake-case",
                    "subject uses snake_case 'vital_status'", path=pp.path,
                    fix="canonical JSON uses 'vitalStatus'")
        for ref in pp.term_refs():
            if term_is_empty(ref.term) and ref.label:
                rep.add("lint", Severity.WARNING, "unnormalised-term",
                        "term {!r} has no ontology id".format(ref.label),
                        path=ref.path,
                        fix="run `phenotk normalise --terms`")
            elif ref.id and ref.id != normalise_prefix(ref.id):
                rep.add("lint", Severity.INFO, "curie-prefix-case",
                        "non-canonical CURIE prefix in {!r}".format(ref.id),
                        path=ref.path)

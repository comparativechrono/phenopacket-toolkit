"""Tests for phenopacket-toolkit, driven by the real example files."""
import glob
import json
import os

import pytest

from phenopacket_toolkit import read, to_json_str
from phenopacket_toolkit.io import readers, writers
from phenopacket_toolkit.model.profile import Dialect
# call the public function API directly (ops/__init__ re-exports these)
from phenopacket_toolkit.ops import (
    deidentify as deidentify_fn,
    diff as diff_fn,
    filter_document,
    normalise as normalise_fn,
    split as split_fn,
    stats as stats_fn,
    validate as validate_fn,
)

DATA = os.path.join(os.path.dirname(__file__), "data")
ALL_FILES = sorted(glob.glob(os.path.join(DATA, "*.json")))
ABUSUA = os.path.join(DATA, "FAM1_family.json")
STUDIO = os.path.join(DATA, "test3_phenopackets.json")
STUDIO_NAMED = os.path.join(DATA, "test3disease_phenopackets.json")


def test_files_present():
    assert len(ALL_FILES) == 6


@pytest.mark.parametrize("path", ALL_FILES)
def test_reads_and_detects_dialect(path):
    doc = read(path)
    assert doc.kind == "family"
    assert doc.id == "FAM1"
    assert doc.source.dialect in Dialect.ALL


def test_dialect_detection():
    assert read(ABUSUA).source.dialect == Dialect.ABUSUA
    assert read(STUDIO).source.dialect == Dialect.STUDIO


def test_abusua_vital_status_canonicalised():
    prob = read(ABUSUA).proband()
    assert "vitalStatus" in prob.subject.raw
    assert "vital_status" not in prob.subject.raw


def test_studio_metadata_inherited_on_read():
    doc = read(STUDIO)
    assert all(pp.has_metadata for pp in doc.phenopackets())


@pytest.mark.parametrize("path", ALL_FILES)
def test_roundtrip_preserve_dialect(path):
    doc = read(path)
    text = to_json_str(doc, dialect=doc.source.dialect)
    doc2 = readers.loads(text, dialect=doc.source.dialect)
    assert diff_fn(doc, doc2, ignore=["order"]) == []


def test_studio_roundtrip_strips_inherited_metadata():
    doc = read(STUDIO)
    raw = json.loads(to_json_str(doc, dialect=Dialect.STUDIO))
    assert "metaData" not in raw["proband"]
    assert "_ppktk_inherited_metadata" not in json.dumps(raw)


def test_consanguinity_field_preserved():
    doc = read(ABUSUA)
    assert "consanguinousParents" in doc.raw
    assert "consanguinousParents" in to_json_str(doc, dialect=Dialect.GA4GH)


def test_cross_dialect_equivalence_after_structural_normalise():
    a, _ = normalise_fn(read(os.path.join(DATA, "FAM1_family.json")),
                        terms=False, structure=True)
    b, _ = normalise_fn(read(os.path.join(DATA, "FAM1nonames_family.json")),
                        terms=False, structure=True)
    assert diff_fn(a, b, ignore=["order", "provenance", "dialect"]) == []


def test_validate_studio_flags_missing_metadata_at_structural_level():
    raw = json.load(open(STUDIO))
    from phenopacket_toolkit.model.document import Document
    from phenopacket_toolkit.model.profile import SourceProfile
    doc = Document(raw, SourceProfile(dialect=Dialect.GA4GH))  # skip adapter
    rep = validate_fn(doc, level="structural")
    assert any(f.code == "missing-metadata" for f in rep.findings)


def test_validate_clean_family_has_no_errors():
    rep = read(ABUSUA).validate(level="reference")
    assert rep.ok, [f.to_dict() for f in rep.errors]


def test_validate_detects_dangling_parent():
    doc = read(ABUSUA)
    doc.raw["pedigree"]["persons"][1]["paternalId"] = "ghost"
    rep = doc.validate(level="reference")
    assert any(f.code == "dangling-parent" for f in rep.errors)


def test_validate_detects_unnormalised_terms():
    rep = read(ABUSUA).validate(level="lint")
    assert any(f.code == "unnormalised-term" for f in rep.findings)


def test_stats_counts():
    res = stats_fn(read(ABUSUA))
    assert res.n_individuals == 16
    assert res.by_affected.get("AFFECTED", 0) > 0
    assert res.n_unnormalised > 0


def test_filter_by_nonmatching_term_drops_all():
    out = filter_document(read(ABUSUA), terms=["HP:0000000"])
    r = stats_fn(out)
    assert r.n_phenotypes + r.n_diseases == 0


def test_filter_proband_only():
    out = filter_document(read(ABUSUA), proband_only=True)
    pps = list(out.phenopackets())
    assert len(pps) == 1 and pps[0].role == "proband"


def test_filter_affected_only_keeps_affected_subjects():
    doc = read(ABUSUA)
    out = filter_document(doc, affected_only=True)
    aff = {p.individual_id: p.affected_status for p in doc.pedigree().persons}
    for pp in out.phenopackets():
        assert aff.get(pp.subject.id) == "AFFECTED"


def test_deidentify_remaps_ids_consistently():
    res = deidentify_fn(read(STUDIO_NAMED), remap_ids="seq")
    assert res.warnings == []
    text = to_json_str(res.document, dialect=Dialect.GA4GH)
    assert "bob" not in text
    ids = {p.individual_id for p in res.document.pedigree().persons}
    for p in res.document.pedigree().persons:
        for pid in (p.paternal_id, p.maternal_id):
            assert pid == "0" or pid in ids


def test_deidentify_drops_dob():
    doc = read(ABUSUA)
    doc.proband().subject.raw["dateOfBirth"] = "1990-01-01T00:00:00Z"
    res = deidentify_fn(doc, drop_dob=True)
    assert "dateOfBirth" not in res.document.proband().subject.raw


def test_deidentify_crosswalk_bijective():
    res = deidentify_fn(read(STUDIO_NAMED), remap_ids="seq")
    assert len(set(res.crosswalk.values())) == len(res.crosswalk)


def test_normalise_mapping_fills_ids():
    mapping = {"diabetes": "MONDO:0005015", "sickle cell": "MONDO:0011382",
               "long qt interval": "HP:0001657"}
    out, log = normalise_fn(read(ABUSUA), terms=True, structure=True,
                            mapping=mapping, use_ontology=False)
    assert log.unresolved == []
    prefixes = {r["namespacePrefix"] for r in out.raw["metaData"]["resources"]}
    assert {"HP", "MONDO"} <= prefixes
    rep = out.validate(level="lint")
    assert not any(f.code == "unnormalised-term" for f in rep.findings)


def test_normalise_no_guess_leaves_unmapped_empty():
    out, log = normalise_fn(read(ABUSUA), terms=True, structure=False,
                            mapping={"diabetes": "MONDO:0005015"},
                            use_ontology=False)
    assert "sickle cell" in log.unresolved
    assert "long qt interval" in log.unresolved


def test_normalise_idempotent():
    mapping = {"diabetes": "MONDO:0005015", "sickle cell": "MONDO:0011382",
               "long qt interval": "HP:0001657"}
    once, _ = normalise_fn(read(ABUSUA), mapping=mapping, use_ontology=False)
    twice, _ = normalise_fn(once, mapping=mapping, use_ontology=False)
    assert diff_fn(once, twice, ignore=["order"]) == []


def test_split_then_count():
    doc = read(ABUSUA)
    parts = split_fn(doc)
    assert len(parts) == len(list(doc.phenopackets()))
    assert all(p.kind == "phenopacket" for p in parts)
    assert all(p.proband().has_metadata for p in parts)


def test_ped_export_person_count():
    ped = writers.to_ped(read(ABUSUA))
    assert len([l for l in ped.splitlines() if l.strip()]) == 16


def test_tsv_export_has_header():
    assert writers.to_tsv(read(ABUSUA)).splitlines()[0].startswith("individual_id\t")


def test_convert_to_abusua_dialect_uses_snake_case():
    assert "vital_status" in to_json_str(read(ABUSUA), dialect=Dialect.ABUSUA)

"""Tests for phenopacket-toolkit 0.4: one form of GA4GH file, read and written through pedigree-ga4gh.

The Okafor family in tests/data is fictional (from the Hearn lab's pedigree practical); its GA4GH Pedigree and
Phenopackets Family were written by studio2ga4gh 0.4.0.
"""
import json
import os
import tempfile

from phenopacket_toolkit import LegacyFileError, from_dict, read
from phenopacket_toolkit.cli.main import main as phenotk
from phenopacket_toolkit.io import writers
from phenopacket_toolkit.ops import (deidentify, filter_document, merge, normalise, render, split, stats, to_kind,
                                     validate)
from pedigree_ga4gh import loads

DATA = os.path.join(os.path.dirname(__file__), "data")
CREATED = "2026-10-17T12:00:00Z"


def files(name="okafor"):
    """The family's GA4GH Pedigree and Phenopackets Family, as documents."""
    out = []
    for kind in ("ga4gh-pedigree", "phenopackets-family"):
        with open(os.path.join(DATA, "{}_{}.json".format(name, kind)), encoding="utf-8") as fh:
            out.append(from_dict(loads(fh.read())))
    return tuple(out)


def test_kinds():
    ped, fam = files()
    assert ped.kind == "pedigree" and fam.kind == "family"
    assert len(list(ped.phenopackets())) == 16
    assert ped.proband().subject.id == "IV-3"
    assert len(ped.relationships()) == 26


def test_validate_both():
    ped, fam = files()
    assert validate(ped).ok and validate(fam).ok


def test_old_files_are_refused_then_upgraded():
    path = os.path.join(DATA, "legacy", "studio2ga4gh-0.3_phenopackets.json")
    try:
        read(path)
    except LegacyFileError as exc:
        assert "phenotk upgrade" in str(exc)
    else:
        raise AssertionError("an old file was read without complaint")
    doc = read(path, allow_legacy=True)
    assert doc.kind == "family"


def test_normalise_fills_terms_from_a_mapping():
    from pedigree_ga4gh import upgrade
    old = read(os.path.join(DATA, "legacy", "studio2ga4gh-0.3_phenopackets.json"), allow_legacy=True)
    data, _changes, _todo = upgrade(old.raw, created=CREATED)
    fam = from_dict(data)
    report = validate(fam)
    assert not report.ok and {f.code for f in report.errors} == {"empty-term-id"}
    mapping = {"Hearing loss from birth": {"id": "HP:0000365", "label": "Hearing impairment"},
               "breast cancer": "MONDO:0007254"}
    out, log = normalise(fam, mapping=mapping, use_ontology=False, versions={"HP": "2026-09-01"})
    assert validate(out).ok, [f.message for f in validate(out).errors]
    assert set(log.resolved) == {"Hearing loss from birth", "Breast cancer"}
    res = {r["namespacePrefix"]: r for r in out.raw["metaData"]["resources"]}
    assert res["HP"]["version"] == "2026-09-01"
    # the older file had hearing loss as a disease: with its HPO term, it is a phenotypic feature
    for pp in out.phenopackets():
        assert all(not d["term"]["id"].startswith("HP:") for d in pp.raw.get("diseases", []))
    assert any(f["type"]["id"] == "HP:0000365" for pp in out.phenopackets() for f in pp.raw.get("phenotypicFeatures", []))
    # the releases recorded in a terms file are used for the resources
    with open(os.path.join(DATA, "example-terms.json"), encoding="utf-8") as fh:
        terms = json.load(fh)
    out, log = normalise(fam, mapping=terms, use_ontology=False)
    assert validate(out).ok
    res = {r["namespacePrefix"]: r for r in out.raw["metaData"]["resources"]}
    assert res["HP"]["version"] == terms["Hearing loss from birth"]["version"]
    assert res["MONDO"]["version"] == terms["Breast cancer"]["version"]


def test_deidentify_a_pedigree_keeps_the_graph():
    ped, fam = files()
    result = deidentify(ped, remap_ids="seq")
    out = result.document
    assert validate(out).ok
    ids = {pp.subject.id for pp in out.phenopackets()}
    assert all(i.startswith("IND-") for i in ids)
    assert all(r.individual in ids and r.relative in ids for r in out.relationships())
    assert all(i in ids for i in out.index_patients())
    assert len(result.crosswalk) == 16


def test_deidentify_replaces_the_ids_in_the_narrative():
    ped, fam = files()
    assert "proband IV-3" in ped.raw["narrative"]
    result = deidentify(ped, remap_ids="seq")
    text = result.document.raw["narrative"]
    new = result.crosswalk["IV-3"]
    assert "proband " + new in text
    # no old id is left, whole or in part (II-1 inside III-1 must not be touched)
    import re
    assert not re.search(r"(?<![\w-])[IV]+-\d+(?![\w-])", text)
    assert any("narrative" in w for w in result.warnings)
    # bare numbers as ids: the narrative is left alone, with a warning
    doc = from_dict(json.loads(json.dumps(ped.raw)))
    doc.raw["narrative"] = "3 people; proband 3."
    for i, pp in enumerate(doc.phenopackets(), 1):
        pp.subject.raw["id"] = str(i)
    doc.raw["relationships"] = []
    doc.raw["indexPatients"] = ["3"]
    result = deidentify(doc, remap_ids="seq")
    assert result.document.raw["narrative"] == "3 people; proband 3."
    assert any("bare numbers" in w for w in result.warnings)


def test_filter_a_pedigree_drops_dangling_relationships():
    ped, fam = files()
    out = filter_document(ped, affected_only=True)
    ids = {pp.subject.id for pp in out.phenopackets()}
    assert ids == {"II-3", "IV-3", "IV-4"}
    assert all(r.individual in ids and r.relative in ids for r in out.relationships())
    assert validate(out).ok


def test_convert_between_pedigree_and_family():
    ped, fam = files()
    fam2, warnings = to_kind(ped, "family")
    assert validate(fam2).ok
    assert fam2.raw["proband"]["subject"]["id"] == "IV-3"
    ped2, warnings = to_kind(fam, "pedigree")
    assert validate(ped2).ok
    assert len(ped2.relationships()) >= 24


def test_ped_from_a_pedigree():
    ped, fam = files()
    rows = [line.split("\t") for line in writers.to_ped(ped).splitlines()]
    assert len(rows) == 16
    child = [r for r in rows if r[1] == "IV-3"][0]
    assert child[2] == "III-2" and child[3] == "III-3" and child[5] == "2"


def test_split_and_merge():
    ped, fam = files()
    parts = split(fam)
    assert parts and all(validate(p).ok for p in parts)
    cohort = merge(parts, into="cohort", cohort_id="C1")
    assert cohort.kind == "cohort" and validate(cohort).ok


def test_stats_and_view():
    ped, fam = files()
    s = stats(ped)
    assert s.n_individuals == 16 and s.relationships["isBiologicalMotherOf"] == 12
    text = render(ped)
    assert "relationships:" in text and "isMonozygoticMultipleBirthSiblingOf" in text


def test_command_line():
    ped, fam = files()
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "ped.json")
        writers.write(ped, p)
        assert phenotk(["validate", p]) == 0
        out = os.path.join(tmp, "fam.json")
        assert phenotk(["convert", p, "--to", "family", "-o", out]) == 0
        assert read(out).kind == "family"
        old = os.path.join(DATA, "legacy", "abusua2ga4gh-0.2_ga4gh.json")
        new = os.path.join(tmp, "up.json")
        assert phenotk(["upgrade", old, "-o", new]) == 0
        assert read(new).kind == "pedigree"
        assert phenotk(["validate", old]) == 2


def test_a_looked_up_match_must_be_close():
    """OLS scores its results by rank (100, 96 ...): normalise must score them by how well they match."""
    from types import SimpleNamespace

    from phenopacket_toolkit.ontology import backends
    from phenopacket_toolkit.ontology.policy import AutoAcceptPolicy

    class FakeOls:  # what hponorm's Suggester gives back from OLS, without asking OLS
        name = "ols"

        def __init__(self, labels):
            self.labels = labels

        def suggest(self, label, limit=8):
            return [SimpleNamespace(id="HP:{:07d}".format(i + 1), label=lab, score=round(100.0 - i * 4, 1),
                                    matched_on="OLS relevance", source="ols") for i, lab in enumerate(self.labels)]

    policy = AutoAcceptPolicy(threshold=0.9)
    be = backends._SuggesterBackend(FakeOls(["Hearing impairment", "Sensorineural hearing impairment"]), "ols")
    assert policy.choose(be.suggest("Hearing loss from birth")) is None      # the first result is not a match
    be = backends._SuggesterBackend(FakeOls(["Abnormality of the ear", "Hearing impairment"]), "ols")
    best = policy.choose(be.suggest("hearing  impairment"))                  # case and spacing do not count
    assert best is not None and best.label == "Hearing impairment"
    assert backends.similarity("Breast cancer", "breast cancer") == 1.0


def test_merge_keeps_the_pedigree_and_the_releases():
    ped, fam = files()
    people = split(ped, affected_only=True)
    # back into a Family, with the GA4GH Pedigree among the inputs: the parents come from its relationships, and
    # the people in both are kept once
    notes = []
    new = merge(people + [ped], into="family", cohort_id="FAM1", notes=notes)
    persons = {p["individualId"]: p for p in new.raw["pedigree"]["persons"]}
    assert persons["IV-3"]["paternalId"] == "III-2" and persons["IV-3"]["maternalId"] == "III-3"
    assert validate(new).ok, [f.message for f in validate(new).errors]
    assert len(notes) == 3 and all("more than one file" in n for n in notes)
    # two families' probands into a Cohort: the same pedigree number is two people
    other = from_dict(json.loads(json.dumps(fam.raw).replace('"FAM1', '"FAM2')))
    notes = []
    both = merge([fam, other], into="cohort", cohort_id="probands", notes=notes)
    ids = [m["subject"]["id"] for m in both.raw["members"]]
    assert len(ids) == len(set(ids)) and "FAM2-IV-3" in ids
    assert validate(both).ok, [f.message for f in validate(both).errors]
    # a Cohort's metaData keeps the release of every ontology its members use
    cohort = merge(people, into="cohort", cohort_id="affected")
    res = {r["namespacePrefix"]: r["version"] for r in cohort.raw["metaData"]["resources"]}
    assert set(res) == {"HP", "MONDO"} and "unknown" not in res.values()


def test_filtering_a_family_keeps_its_pedigree_valid():
    ped, fam = files()
    # terms only: everyone stays, in the Phenopackets and in the pedigree
    new = filter_document(fam, terms=["HP:0000365"], prune_pedigree=True)
    assert len(new.raw["pedigree"]["persons"]) == len(fam.raw["pedigree"]["persons"])
    assert validate(new).ok, [f.message for f in validate(new).errors]
    assert all(t.id == "HP:0000365" for pp in new.phenopackets() for t in pp.term_refs())
    # the proband only: the relatives with Phenopackets leave the pedigree too, and no line points to them
    new = filter_document(fam, proband_only=True, prune_pedigree=True)
    ids = {p["individualId"] for p in new.raw["pedigree"]["persons"]}
    assert "IV-3" in ids and "IV-4" not in ids and "II-3" not in ids
    assert validate(new).ok, [f.message for f in validate(new).errors]


def test_hiding_the_provenance_keeps_the_file_valid():
    ped, fam = files()
    res = deidentify(fam, remap_ids="seq", drop_provenance=True)
    assert validate(res.document).ok, [f.message for f in validate(res.document).errors]
    for md in [res.document.raw["metaData"]] + [pp.raw["metaData"] for pp in res.document.phenopackets()]:
        assert md["createdBy"] == "phenotk deidentify" and md["created"] != CREATED


def test_add_declares_its_ontologies_and_names_the_right_person():
    from phenopacket_toolkit.ops import add
    ped, fam = files()
    new = add(fam, "IV-4", diseases=[{"id_": "MONDO:0009061", "label": "cystic fibrosis"}])
    assert validate(new).ok, [f.message for f in validate(new).errors]
    # a variant: the interpretation is of the person it is added to, with its zygosity's label
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "fam.json")
        out = os.path.join(tmp, "out.json")
        with open(src, "w", encoding="utf-8") as fh:
            json.dump(fam.raw, fh)
        assert phenotk(["add", src, "--target", "IV-4", "--variant", "--gene", "HGNC:1884=CFTR", "--zygosity",
                        "GENO:0000135", "--diagnosis", "MONDO:0009061=cystic fibrosis", "-o", out]) == 0
        doc = read(out)
        assert validate(doc).ok, [f.message for f in validate(doc).errors]
        pp = next(p for p in doc.phenopackets() if p.subject.id == "IV-4")
        gi = pp.raw["interpretations"][0]["diagnosis"]["genomicInterpretations"][0]
        assert gi["subjectOrBiosampleId"] == "IV-4"
        assert gi["variantInterpretation"]["variationDescriptor"]["allelicState"]["label"] == "heterozygous"
        # without a diagnosis, a variant is refused (Diagnosis.disease is required)
        assert phenotk(["add", src, "--variant", "--gene", "HGNC:1884=CFTR", "-o", out]) == 2


def test_filter_refuses_to_leave_a_family_without_its_proband():
    ped, fam = files()
    try:
        filter_document(fam, sex="FEMALE")
    except ValueError as e:
        assert "proband" in str(e)
    else:
        raise AssertionError("a Family without its proband was written")


def test_options_of_version_0_3_are_accepted_and_ignored(capsys):
    path = os.path.join(DATA, "okafor_phenopackets-family.json")
    assert phenotk(["validate", path, "--level", "reference", "--online"]) == 0
    assert "not needed since version 0.4" in capsys.readouterr().err
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.ped")
        assert phenotk(["convert", path, "--to", "ped", "--dialect", "studio", "--to-dialect", "ga4gh",
                        "-o", out]) == 0
        assert os.path.exists(out)
    assert "--dialect and --to-dialect are not needed" in capsys.readouterr().err

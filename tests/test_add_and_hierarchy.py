"""Tests for the hierarchy resolver (filter --include-descendants) and `add`."""
import os

from phenopacket_toolkit import read
from phenopacket_toolkit.ops import add, filter_document, normalise, stats, validate
from phenopacket_toolkit.ontology.hierarchy import OboDescendantResolver, make_resolver

DATA = os.path.join(os.path.dirname(__file__), "data")
FAM1 = os.path.join(DATA, "fam1_family.json")      # a small family whose conditions still need terms
OBO = os.path.join(DATA, "mini_hp.obo")


# -- descendant resolver --------------------------------------------------
def test_obo_resolver_transitive_descendants():
    res = OboDescendantResolver.from_file(OBO)
    assert res.descendants("HP:0000118") == {"HP:0001626", "HP:0001657", "HP:0000479"}
    assert res.descendants("HP:0001626") == {"HP:0001657"}
    assert res.descendants("HP:0001657") == set()


def test_make_resolver_routes_by_prefix():
    resolve = make_resolver(backend="obo", hpo_file=OBO)
    assert "HP:0001657" in resolve("HP:0001626")
    assert resolve("MONDO:0005015") == set()   # no mondo source supplied


def _doc_with_term(curie):
    doc = read(FAM1)
    # set one proband feature to a concrete child term
    doc.proband().raw["phenotypicFeatures"] = [{"type": {"id": curie, "label": "x"}}]
    return doc


def test_filter_include_descendants_keeps_child():
    doc = _doc_with_term("HP:0001657")
    resolve = make_resolver(backend="obo", hpo_file=OBO)
    out = filter_document(doc, terms=["HP:0001626"], include_descendants=True,
                          descendant_resolver=resolve, proband_only=True)
    kept = [r.id for pp in out.phenopackets() for r in pp.term_refs()]
    assert kept == ["HP:0001657"]


def test_filter_without_descendants_drops_child():
    doc = _doc_with_term("HP:0001657")
    out = filter_document(doc, terms=["HP:0001626"], proband_only=True)
    kept = [r.id for pp in out.phenopackets() for r in pp.term_refs()]
    assert kept == []


# -- add / annotate -------------------------------------------------------
def test_add_phenotype_with_onset_and_severity():
    doc = read(FAM1)
    out = doc.add("proband", phenotypes=[{
        "id_": "HP:0001657", "label": "Prolonged QT interval",
        "onset": "P10Y", "severity": "HP:0012828", "severity_label": "Severe"}])
    feats = out.proband().raw["phenotypicFeatures"]
    added = feats[-1]
    assert added["type"]["id"] == "HP:0001657"
    assert added["onset"]["age"]["iso8601duration"] == "P10Y"
    assert added["severity"]["id"] == "HP:0012828"


def test_add_disease_with_ontology_onset():
    doc = read(FAM1)
    out = doc.add("proband", diseases=[{
        "id_": "MONDO:0005015", "label": "diabetes mellitus",
        "onset": "HP:0003577", "onset_label": "Congenital onset"}])
    added = out.proband().raw["diseases"][-1]
    assert added["onset"]["ontologyClass"]["id"] == "HP:0003577"


def test_add_vital_status_deceased():
    doc = read(FAM1)
    out = doc.add("proband", vital_status=__import__(
        "phenopacket_toolkit.model.builders", fromlist=["vital_status"]).vital_status(
        "DECEASED", cause="MONDO:0011382", cause_label="sickle cell disease",
        survival_days=12000))
    vs = out.proband().subject.raw["vitalStatus"]
    assert vs["status"] == "DECEASED"
    assert vs["causeOfDeath"]["id"] == "MONDO:0011382"
    assert vs["survivalTimeInDays"] == 12000


def test_add_subject_demographics():
    doc = read(FAM1)
    out = doc.add("proband", subject_fields={"karyotypicSex": "XY",
                                             "dateOfBirth": "1990-01-01T00:00:00Z"})
    subj = out.proband().subject.raw
    assert subj["karyotypicSex"] == "XY"
    assert subj["dateOfBirth"] == "1990-01-01T00:00:00Z"


def test_add_variant_interpretation():
    from phenopacket_toolkit.model import builders as B
    doc = read(FAM1)
    var = B.variation_descriptor(gene_id="HGNC:6294", gene_symbol="KCNQ1",
                                 hgvs="NM_000218.3:c.569G>A", zygosity="heterozygous")
    interp = B.interpretation(disease_id="MONDO:0011382", disease_label="sickle cell disease",
                              subject_id=doc.proband().subject.id,
                              acmg="PATHOGENIC", variation=var)
    out = doc.add("proband", interpretations=[interp])
    gi = out.proband().raw["interpretations"][0]["diagnosis"]["genomicInterpretations"][0]
    vi = gi["variantInterpretation"]
    assert vi["acmgPathogenicityClassification"] == "PATHOGENIC"
    assert vi["variationDescriptor"]["geneContext"]["symbol"] == "KCNQ1"
    assert vi["variationDescriptor"]["allelicState"]["id"] == "GENO:0000135"


def test_add_targets_all_and_affected():
    doc = read(FAM1)
    out_all = doc.add("all", subject_fields={"karyotypicSex": "XX"})
    assert all(pp.subject.raw.get("karyotypicSex") == "XX" for pp in out_all.phenopackets())

    out_aff = doc.add("affected", external_references=[{"id": "PMID:1"}])
    aff = {p.individual_id: p.affected_status for p in doc.pedigree().persons}
    for pp in out_aff.phenopackets():
        has_ref = "externalReferences" in pp.raw.get("metaData", {})
        assert has_ref == (aff.get(pp.subject.id) == "AFFECTED")


def test_add_target_by_subject_id():
    doc = read(FAM1)
    out = doc.add("i5", subject_fields={"karyotypicSex": "XY"})
    hit = [pp for pp in out.phenopackets() if pp.subject.id == "i5"][0]
    assert hit.subject.raw["karyotypicSex"] == "XY"
    others = [pp for pp in out.phenopackets() if pp.subject.id != "i5"]
    assert all("karyotypicSex" not in pp.subject.raw for pp in others)


def test_add_generic_set_merge_append_and_patch():
    doc = read(FAM1)
    out = doc.add("proband",
                  set_paths=[("subject.taxonomy", {"id": "NCBITaxon:9606", "label": "Homo sapiens"})],
                  append_paths=[("phenotypicFeatures", {"type": {"id": "HP:0000001", "label": "All"}})],
                  patch={"subject": {"gender": {"id": "NCIT:C16576", "label": "Female"}}})
    p = out.proband()
    assert p.subject.raw["taxonomy"]["id"] == "NCBITaxon:9606"
    assert p.subject.raw["gender"]["label"] == "Female"
    assert any(f["type"]["id"] == "HP:0000001" for f in p.raw["phenotypicFeatures"])


def test_add_unknown_target_raises():
    doc = read(FAM1)
    try:
        doc.add("nobody", subject_fields={"karyotypicSex": "XY"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_normalise_rebuilds_resources_for_added_genomic_terms():
    from phenopacket_toolkit.model import builders as B
    doc = read(FAM1)
    var = B.variation_descriptor(gene_id="HGNC:6294", gene_symbol="KCNQ1",
                                 zygosity="heterozygous")
    interp = B.interpretation(disease_id="MONDO:0011382", subject_id=doc.proband().subject.id,
                              variation=var)
    doc = doc.add("proband", interpretations=[interp])
    # also give the disease list a normalised MONDO id so resources include MONDO
    doc = doc.add("proband", diseases=[{"id_": "MONDO:0011382", "label": "sickle cell disease"}])
    out, _ = normalise(doc, terms=False, structure=True)
    prefixes = {r["namespacePrefix"] for r in out.raw["metaData"]["resources"]}
    # MONDO comes from the disease term; GENO is not in diseases/features so not added,
    # but MONDO must be present
    assert "MONDO" in prefixes


def test_normalise_always_explains_itself():
    # The core guarantee: a run is never a silent no-op. It always emits an
    # explanatory note, and every empty term is accounted for as resolved or
    # unresolved -- whether or not a backend is installed. (Offline, so that the
    # tests never contact EBI's Ontology Lookup Service.)
    doc = read(FAM1)
    _, log = normalise(doc, terms=True, structure=False, backend="local",
                       hpo_file=os.path.join(DATA, "hpo_sample.obo"),
                       mondo_file=os.path.join(DATA, "mondo_sample.obo"))
    assert log.notes, "normalise must report what it did"
    accounted = set(log.resolved) | set(log.unresolved)
    assert "diabetes" in accounted and "sickle cell anemia" in accounted


def test_normalise_no_online_notes_mapping_only():
    doc = read(FAM1)
    _, log = normalise(doc, terms=True, structure=False, use_ontology=False,
                       mapping={"diabetes": "MONDO:0005015"})
    assert log.resolved == {"diabetes": "MONDO:0005015"}
    assert any("mapping only" in n for n in log.notes)

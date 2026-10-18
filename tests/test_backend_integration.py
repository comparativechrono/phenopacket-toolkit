"""Integration tests against the real hponorm / mondonorm packages.

They are skipped when the packages are not installed (pip install
"phenopacket-toolkit[test]" installs them). They use the small sample ontologies
in tests/data, so they never go online.
"""
import json
import os
from types import SimpleNamespace

from phenopacket_toolkit import from_dict, read
from phenopacket_toolkit.ops import normalise

DATA = os.path.join(os.path.dirname(__file__), "data")
HPO = os.path.join(DATA, "hpo_sample.obo")
MONDO = os.path.join(DATA, "mondo_sample.obo")


def _has(pkg):
    try:
        __import__(pkg + ".suggest")
        return True
    except Exception:
        import pytest
        pytest.skip(pkg + " is not installed")


def test_mondo_backend_fills_disease_ids():
    if not _has("mondonorm"):
        return
    doc = read(os.path.join(DATA, "fam1_family.json"))
    out, log = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO, structure=True)
    assert log.resolved.get("diabetes") == "MONDO:0005015"
    assert log.resolved.get("sickle cell anemia") == "MONDO:0011382"
    assert "long qt interval" in log.unresolved          # no-guess: not in this MONDO
    assert any("looked up with mondonorm" in n for n in log.notes)
    # the proband disease is now a real CURIE
    assert out.proband().raw["diseases"][0]["term"]["id"] == "MONDO:0005015"


def test_hpo_backend_fills_phenotype_ids():
    if not _has("hponorm"):
        return
    doc = read(os.path.join(DATA, "fam1_phenotypes_family.json"))
    out, log = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO, structure=False)
    assert log.resolved.get("diabetes", "").startswith("HP:")
    assert "sickle cell anemia" in log.unresolved        # not an HPO phenotype


def test_score_scaling_applies_threshold():
    if not _has("mondonorm"):
        return
    doc = read(os.path.join(DATA, "fam1_family.json"))
    # a threshold above 1 rejects everything, even the term's own label (1.0)
    out, log = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO,
                         threshold=1.01, structure=False)
    assert log.resolved == {}                            # nothing clears >1.0
    # the default (0.98) accepts the exact synonyms: "diabetes" is one of diabetes mellitus's
    out2, log2 = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO, structure=False)
    assert log2.resolved.get("diabetes") == "MONDO:0005015"
    assert log2.resolved.get("sickle cell anemia") == "MONDO:0011382"


def test_a_look_up_that_gets_no_answer_is_noted(monkeypatch):
    """hponorm and mondonorm 1.1 say when OLS did not answer; normalise passes that on."""
    from phenopacket_toolkit.ontology import backends

    class Silent:
        name = "ols"
        last_error = "OLS did not answer (timed out)"

        def suggest(self, label, limit=8):
            return []

    monkeypatch.setattr(backends, "mondo_backend", lambda **kw: backends._SuggesterBackend(Silent(), "ols"))
    monkeypatch.setattr(backends, "hpo_backend", lambda **kw: backends._SuggesterBackend(Silent(), "ols"))
    doc = read(os.path.join(DATA, "fam1_family.json"))
    _, log = normalise(doc, backend="ols")
    assert any("got no answer: OLS did not answer" in n for n in log.notes)
    assert log.unresolved


def _family(phenotypes=(), diseases=()):
    """The sample family, with only these names to look up, all on the proband."""
    with open(os.path.join(DATA, "fam1_phenotypes_family.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    data["relatives"][0].pop("phenotypicFeatures", None)
    proband = data["proband"]
    proband["phenotypicFeatures"] = [{"type": {"id": "", "label": name}} for name in phenotypes]
    if diseases:
        proband["diseases"] = [{"term": {"id": "", "label": name}} for name in diseases]
    return from_dict(data)


class Offers:
    """A suggester that offers the same results for any name, as (id, label, score, matched_on)."""

    name = "local"

    def __init__(self, *found):
        self.found = [SimpleNamespace(id=i, label=lab, score=score, matched_on=on) for i, lab, score, on in found]

    def suggest(self, label, limit=8):
        return list(self.found)


def test_the_opposite_term_is_not_filled_in():
    """"Maternal hypothyroidism" and "Essential hypotension" are spelt almost like terms that mean the opposite."""
    if not (_has("hponorm") and _has("mondonorm")):
        return
    doc = _family(phenotypes=["Maternal hypothyroidism"], diseases=["Essential hypotension"])
    out, log = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO, structure=False)
    # HP:0034778 Maternal hyperthyroidism and MONDO:0001134 essential hypertension are in the samples
    assert log.resolved == {}
    assert sorted(log.unresolved) == ["Essential hypotension", "Maternal hypothyroidism"]
    assert out.proband().raw["phenotypicFeatures"][0]["type"]["id"] == ""
    assert out.proband().raw["diseases"][0]["term"]["id"] == ""
    # the terms' own names are filled in
    doc = _family(phenotypes=["maternal hyperthyroidism"], diseases=["Essential hypertension"])
    _, log = normalise(doc, backend="local", hpo_file=HPO, mondo_file=MONDO, structure=False)
    assert log.resolved == {"maternal hyperthyroidism": "HP:0034778", "Essential hypertension": "MONDO:0001134"}


def test_a_name_spelt_like_another_term_is_not_filled_with_it(monkeypatch):
    """However a backend scores "Maternal hyperthyroidism" for "Maternal hypothyroidism", it is not filled in."""
    from phenopacket_toolkit.ontology import backends

    doc = _family(phenotypes=["Maternal hypothyroidism"])
    for score, matched_on, exact_scores in ((93.6, "label", False),           # hponorm 1.0's own search
                                            (100.0, "OLS relevance", False),  # 1.0's first result from OLS
                                            (25.0, "label", True)):           # hponorm 1.1
        offers = Offers(("HP:0034778", "Maternal hyperthyroidism", score, matched_on))
        monkeypatch.setattr(backends, "hpo_backend",
                            lambda **kw: backends._SuggesterBackend(offers, "local", exact_scores=exact_scores))
        out, log = normalise(doc, backend="local", structure=False)
        assert log.resolved == {} and log.unresolved == ["Maternal hypothyroidism"], matched_on
        assert out.proband().raw["phenotypicFeatures"][0]["type"]["id"] == ""
    # a lower threshold accepts it, as the guess it is, and the log says to check it
    offers = Offers(("HP:0034778", "Maternal hyperthyroidism", 93.6, "label"))
    monkeypatch.setattr(backends, "hpo_backend", lambda **kw: backends._SuggesterBackend(offers, "local"))
    _, log = normalise(doc, backend="local", structure=False, threshold=0.9)
    assert log.resolved == {"Maternal hypothyroidism": "HP:0034778"}
    assert any("close match (0.94)" in n and "check it" in n for n in log.notes)


def test_the_default_accepts_a_term_s_own_name_from_either_version():
    from phenopacket_toolkit.ontology import backends
    from phenopacket_toolkit.ontology.policy import EXACT_MATCH, AutoAcceptPolicy

    policy = AutoAcceptPolicy()
    assert policy.threshold == EXACT_MATCH == 0.98

    def chosen(name, *found, exact_scores=False):
        best = policy.choose(backends._SuggesterBackend(Offers(*found), exact_scores=exact_scores).suggest(name))
        return best and best.id

    # hponorm 1.0's results from OLS, scored by rank, are scored by their labels: the exact label passes
    assert chosen("hypertension", ("HP:0002615", "Hypotension", 100.0, "OLS relevance"),
                  ("HP:0000822", "Hypertension", 96.0, "OLS relevance")) == "HP:0000822"
    assert chosen("Maternal hypothyroidism", ("HP:0034778", "Maternal hyperthyroidism", 100.0, "OLS relevance")) is None
    # 1.0's own search: the label (100) and an exact synonym (98) pass
    assert chosen("Hypertension", ("HP:0000822", "Hypertension", 100.0, "label")) == "HP:0000822"
    assert chosen("Diabetes", ("MONDO:0005015", "diabetes mellitus", 98.0, "synonym: Diabetes")) == "MONDO:0005015"
    # ... but not a long name with a character or two changed, which 1.0 scores as high: here mondonorm 1.0's
    # first result, with the full Mondo, for a name that is none of the subtypes
    name = "autosomal recessive limb-girdle muscular dystrophy type 2"
    other = ("MONDO:0100582", "TOR1AIP1-related myopathy", 99.1,
             "synonym: autosomal recessive limb-girdle muscular dystrophy type 2Y")
    assert chosen(name, other) is None
    assert backends._SuggesterBackend(Offers(other)).suggest(name)[0].score == backends.NOT_EXACT
    # 1.1 keeps its scores of 98 and more for exact matches, by its own rules (possessives, accents ...)
    assert chosen("Huntington's disease", ("MONDO:0007739", "Huntington disease", 100.0, "label"),
                  exact_scores=True) == "MONDO:0007739"
    # names that are not the same words are never given more than 0.97, however alike they are
    assert backends.similarity(name, name + "Y") == backends.NOT_EXACT == 0.97
    assert backends.similarity("Breast  cancer.", "breast cancer") == 1.0

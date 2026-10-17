"""Integration tests against the real hponorm / mondonorm packages.

These skip cleanly (return early) when the packages are not installed, so the
suite still passes in a core-only environment.
"""
import os

from phenopacket_toolkit import read
from phenopacket_toolkit.ops import normalise

DATA = os.path.join(os.path.dirname(__file__), "data")
HPO = os.path.join(DATA, "hpo_sample.obo")
MONDO = os.path.join(DATA, "mondo_sample.obo")


def _has(pkg):
    try:
        __import__(pkg + ".suggest")
        return True
    except Exception:
        return False


def test_mondo_backend_fills_disease_ids():
    if not _has("mondonorm"):
        return
    doc = read(os.path.join(DATA, "FAM1_family.json"))
    out, log = normalise(doc, backend="local", mondo_file=MONDO, structure=True)
    assert log.resolved.get("diabetes") == "MONDO:0005015"
    assert log.resolved.get("sickle cell") == "MONDO:0011382"
    assert "long qt interval" in log.unresolved          # no-guess: not in this MONDO
    assert any("backend ready" in n for n in log.notes)
    # the proband disease is now a real CURIE
    assert out.proband().raw["diseases"][0]["term"]["id"] == "MONDO:0005015"


def test_hpo_backend_fills_phenotype_ids():
    if not _has("hponorm"):
        return
    doc = read(os.path.join(DATA, "FAM1phenotypes_family.json"))
    out, log = normalise(doc, backend="local", hpo_file=HPO, structure=False)
    assert log.resolved.get("diabetes", "").startswith("HP:")
    assert "sickle cell" in log.unresolved               # not an HPO phenotype


def test_score_scaling_applies_threshold():
    if not _has("mondonorm"):
        return
    doc = read(os.path.join(DATA, "FAM1_family.json"))
    # an impossibly high threshold rejects even an exact (1.0) match? no - exact==1.0
    out, log = normalise(doc, backend="local", mondo_file=MONDO,
                         threshold=1.01, structure=False)
    assert log.resolved == {}                            # nothing clears >1.0
    # a normal threshold accepts the exact synonym hits
    out2, log2 = normalise(doc, backend="local", mondo_file=MONDO,
                           threshold=0.9, structure=False)
    assert log2.resolved.get("diabetes") == "MONDO:0005015"

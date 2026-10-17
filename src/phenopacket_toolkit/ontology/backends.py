"""Adapters over the real hponorm / mondonorm packages.

These packages expose their classes in *submodules* (the top-level package has
no public attributes), and their ranked ``Candidate.score`` is on a 0-100 scale.
This adapter therefore:

  * imports ``Suggester`` / index / ``OlsClient`` from the correct submodules,
  * builds a ``Suggester`` following each package's own ``build_suggester`` logic
    (auto -> OLS if reachable else local; local -> Index.load; ols -> OlsClient),
  * rescales scores to 0-1 so our AutoAcceptPolicy threshold (e.g. 0.9) is
    interpretable as "90% match or better".

We never invoke their interactive CLI.
"""
from __future__ import annotations

from typing import List, Optional

from .policy import Candidate


class _SuggesterBackend:
    def __init__(self, suggester, name: str = ""):
        self._s = suggester
        self.name = name or getattr(suggester, "name", "backend")

    def suggest(self, label: str, limit: int = 8) -> List[Candidate]:
        out: List[Candidate] = []
        for c in self._s.suggest(label, limit=limit):
            # hponorm/mondonorm Candidate.score is on a 0-100 scale; rescale to
            # 0-1 so AutoAcceptPolicy thresholds read as "fraction matched".
            score = float(getattr(c, "score", 0.0)) / 100.0
            out.append(Candidate(id=getattr(c, "id", ""),
                                 label=getattr(c, "label", ""),
                                 score=score))
        return out


def _import(module_name: str):
    try:
        suggest = __import__(module_name + ".suggest", fromlist=["Suggester"])
        ols = __import__(module_name + ".ols", fromlist=["OlsClient"])
    except ImportError as exc:
        raise RuntimeError(
            "{name} normalisation needs {pkg}: "
            "pip install 'phenopacket-toolkit[normalise]'  ({err})".format(
                name="phenotype" if module_name == "hponorm" else "disease",
                pkg=module_name, err=exc))
    return suggest, ols


def _build(module_name: str, index_attr_module: str, index_cls: str,
           backend: str, local_file: Optional[str]) -> _SuggesterBackend:
    suggest_mod, ols_mod = _import(module_name)
    Suggester = suggest_mod.Suggester
    OlsClient = ols_mod.OlsClient
    idx_mod = __import__(module_name + "." + index_attr_module, fromlist=[index_cls])
    Index = getattr(idx_mod, index_cls)

    if backend == "ols":
        return _SuggesterBackend(Suggester(OlsClient(), name="ols"), "ols")

    if backend == "local" or local_file:
        idx = Index.load(local_file) if local_file else Index.load()
        return _SuggesterBackend(Suggester(idx, name="local"), "local")

    # auto: prefer OLS when reachable, else fall back to a local index
    ols = OlsClient()
    try:
        if ols.available():
            return _SuggesterBackend(Suggester(ols, name="ols"), "ols")
    except Exception:
        pass
    idx = Index.load()       # may download/cache; raises offline with no cache
    return _SuggesterBackend(Suggester(idx, name="local"), "local")


def hpo_backend(*, backend: str = "auto", hpo_file: Optional[str] = None) -> _SuggesterBackend:
    return _build("hponorm", "hpo", "HpoIndex", backend, hpo_file)


def mondo_backend(*, backend: str = "auto", mondo_file: Optional[str] = None) -> _SuggesterBackend:
    return _build("mondonorm", "mondo", "MondoIndex", backend, mondo_file)

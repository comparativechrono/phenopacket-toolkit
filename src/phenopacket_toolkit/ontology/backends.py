"""Adapters over the real hponorm / mondonorm packages.

These packages expose their classes in *submodules* (the top-level package has
no public attributes), and their ranked ``Candidate.score`` is on a 0-100 scale.
This adapter therefore:

  * imports ``Suggester`` / index / ``OlsClient`` from the correct submodules,
  * builds a ``Suggester`` following each package's own ``build_suggester`` logic
    (auto -> OLS if reachable else local; local -> Index.load; ols -> OlsClient),
  * rescales scores to 0-1 so our AutoAcceptPolicy threshold (e.g. 0.9) is
    interpretable as "90% match or better",
  * and scores EBI's Ontology Lookup Service's results by how closely their
    labels match the name: hponorm's and mondonorm's OLS clients score them by
    rank (100, 96, 92 ...), which would make the first result look like an
    exact match whatever it was.

We never invoke their interactive CLI.
"""
from __future__ import annotations

import difflib
import re
from typing import List, Optional

from .policy import Candidate

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def obo_version(path: Optional[str]) -> str:
    """The release date in an OBO file's ``data-version`` header ('' if none)."""
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("data-version:"):
                    m = _DATE.search(line)
                    return m.group(1) if m else line.split(":", 1)[1].strip()
                if line.startswith('"graphs"') or line.startswith("[Term]"):
                    break
    except OSError:
        return ""
    return ""


def ols_version(client, ontology: str) -> str:
    """The release OLS is serving for an ontology ('' if it cannot be found)."""
    try:
        data = client._get_json("{}/ontologies/{}".format(client.base, ontology))
    except Exception:  # noqa: BLE001
        return ""
    cfg = data.get("config") or {}
    v = cfg.get("version") or data.get("version") or ""
    if not v:
        m = _DATE.search(cfg.get("versionIri") or "")
        v = m.group(1) if m else ""
    m = _DATE.search(v or "")
    return m.group(1) if m else (v or "")


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def similarity(name: str, label: str) -> float:
    """How closely a term's label matches a name, from 0 to 1 (1: the same words, whatever the case and punctuation)."""
    a, b = _words(name), _words(label)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


class _SuggesterBackend:
    def __init__(self, suggester, name: str = "", version: str = ""):
        self._s = suggester
        self.name = name or getattr(suggester, "name", "backend")
        self.version = version
        self.last_error: Optional[str] = None

    def suggest(self, label: str, limit: int = 8) -> List[Candidate]:
        out: List[Candidate] = []
        found = self._s.suggest(label, limit=limit)
        # hponorm and mondonorm 1.1 say when OLS did not answer, rather than giving no suggestions
        self.last_error = getattr(self._s, "last_error", None) or None
        for c in found:
            if getattr(c, "matched_on", "") == "OLS relevance":
                # OLS's results come scored by their rank, not by how well they match: score the label instead
                score = similarity(label, getattr(c, "label", ""))
            else:
                # hponorm/mondonorm Candidate.score is on a 0-100 scale; rescale to
                # 0-1 so AutoAcceptPolicy thresholds read as "fraction matched".
                score = float(getattr(c, "score", 0.0)) / 100.0
            out.append(Candidate(id=getattr(c, "id", ""),
                                 label=getattr(c, "label", ""),
                                 score=score))
        # the closest first (a stable sort keeps the backend's order among equals)
        out.sort(key=lambda x: -x.score)
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

    onto = "hp" if module_name == "hponorm" else "mondo"
    if backend == "ols":
        client = OlsClient()
        return _SuggesterBackend(Suggester(client, name="ols"), "ols", ols_version(client, onto))

    if backend == "local" or local_file:
        idx = Index.load(local_file) if local_file else Index.load()
        return _SuggesterBackend(Suggester(idx, name="local"), "local", obo_version(getattr(idx, "source", None)))

    # auto: prefer OLS when reachable, else fall back to a local index
    ols = OlsClient()
    try:
        if ols.available():
            return _SuggesterBackend(Suggester(ols, name="ols"), "ols", ols_version(ols, onto))
    except Exception:
        pass
    idx = Index.load()       # may download/cache; raises offline with no cache
    return _SuggesterBackend(Suggester(idx, name="local"), "local", obo_version(getattr(idx, "source", None)))


def hpo_backend(*, backend: str = "auto", hpo_file: Optional[str] = None) -> _SuggesterBackend:
    return _build("hponorm", "hpo", "HpoIndex", backend, hpo_file)


def mondo_backend(*, backend: str = "auto", mondo_file: Optional[str] = None) -> _SuggesterBackend:
    return _build("mondonorm", "mondo", "MondoIndex", backend, mondo_file)

"""Term-hierarchy resolution for `filter --include-descendants`.

Provides resolvers that expand a CURIE to the set of its descendant (more
specific) terms:

  * OboDescendantResolver  - parses an OBO file's ``is_a`` graph (stdlib only,
    offline). Works with the hp.obo / mondo.obo files that hponorm / mondonorm
    download and cache.
  * OlsDescendantResolver  - queries the EBI Ontology Lookup Service (online).
  * make_resolver(...)     - returns a single callable ``curie -> set[str]`` that
    routes by prefix (HP -> hpo source, MONDO -> mondo source).

A best-effort hook also uses an hponorm/mondonorm index if it happens to expose
a descendant API, but nothing depends on that.
"""
from __future__ import annotations

import importlib

from typing import Callable, Dict, Iterable, Optional, Set

from ..model.curie import normalise_prefix


# -- OBO graph ------------------------------------------------------------
def parse_obo_children(path: str) -> Dict[str, Set[str]]:
    """Return parent_curie -> set(direct child curies) from an .obo file."""
    children: Dict[str, Set[str]] = {}
    current: Optional[str] = None
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line == "[Term]":
                current = None
            elif line.startswith("id:"):
                current = line[3:].strip()
            elif line.startswith("is_a:") and current:
                # "is_a: HP:0000118 ! Phenotypic abnormality"
                parent = line[5:].strip().split("!", 1)[0].strip()
                parent = parent.split(" ", 1)[0].strip()
                if parent:
                    children.setdefault(parent, set()).add(current)
    return children


class OboDescendantResolver:
    def __init__(self, children: Dict[str, Set[str]]):
        self._children = children

    @classmethod
    def from_file(cls, path: str) -> "OboDescendantResolver":
        return cls(parse_obo_children(path))

    def descendants(self, curie: str) -> Set[str]:
        curie = normalise_prefix(curie)
        out: Set[str] = set()
        stack = list(self._children.get(curie, ()))
        while stack:
            node = stack.pop()
            if node in out:
                continue
            out.add(node)
            stack.extend(self._children.get(node, ()))
        return out


# -- OLS (online) ---------------------------------------------------------
class OlsDescendantResolver:
    """Query OLS v4 for descendants. Online; uses urllib (no extra deps)."""

    _ONTO = {"HP": "hp", "MONDO": "mondo"}
    _BASE = "https://www.ebi.ac.uk/ols4/api/ontologies/{onto}/terms/{iri}/descendants?size=500"

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout

    def descendants(self, curie: str) -> Set[str]:
        import json
        import urllib.parse
        import urllib.request

        curie = normalise_prefix(curie)
        prefix = curie.split(":", 1)[0]
        onto = self._ONTO.get(prefix)
        if not onto:
            return set()
        obo_id = curie.replace(":", "_")
        iri = "http://purl.obolibrary.org/obo/" + obo_id
        double = urllib.parse.quote(urllib.parse.quote(iri, safe=""), safe="")
        url = self._BASE.format(onto=onto, iri=double)
        out: Set[str] = set()
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for term in data.get("_embedded", {}).get("terms", []):
                oid = term.get("obo_id") or term.get("oboId")
                if oid:
                    out.add(normalise_prefix(oid))
        except Exception:
            return set()
        return out


# -- best-effort hponorm/mondonorm index hook -----------------------------
class _IndexResolver:
    def __init__(self, index):
        self._idx = index

    def descendants(self, curie: str) -> Set[str]:
        for meth in ("descendants", "subclasses", "children"):
            fn = getattr(self._idx, meth, None)
            if callable(fn):
                try:
                    return {normalise_prefix(x) for x in fn(curie)}
                except Exception:
                    continue
        return set()


_HIERARCHY = ("descendants", "subclasses", "children")


def _try_index(module_name: str, index_cls: str, local_file: Optional[str]):
    """hponorm's or mondonorm's index, if it can say what a term's descendants are.

    Neither can yet: up to version 1.1 they look terms up by name only, so
    this gives ``None`` and an OBO file or OLS is used instead. It never
    downloads an ontology: only a file that was given, or one already in the
    package's cache, is read. (hponorm and mondonorm 1.0 had no top-level
    index, so this did nothing; from 1.1 they have, and loading one without a
    file would download the whole ontology.)
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    Index = getattr(module, index_cls, None)
    if Index is None or not any(callable(getattr(Index, m, None)) for m in _HIERARCHY):
        return None
    try:
        idx = Index.load(local_file, allow_download=False)
    except Exception:
        return None
    return _IndexResolver(idx)


# -- factory --------------------------------------------------------------
def make_resolver(
    *,
    backend: str = "auto",          # auto | obo | ols
    hpo_file: Optional[str] = None,
    mondo_file: Optional[str] = None,
) -> Callable[[str], Set[str]]:
    """Build a prefix-routing ``curie -> set(descendant curies)`` callable."""
    hpo_res = None
    mondo_res = None

    if backend in ("auto", "obo"):
        if hpo_file:
            hpo_res = OboDescendantResolver.from_file(hpo_file)
        if mondo_file:
            mondo_res = OboDescendantResolver.from_file(mondo_file)
        if hpo_res is None:
            hpo_res = _try_index("hponorm", "HpoIndex", hpo_file)
        if mondo_res is None:
            mondo_res = _try_index("mondonorm", "MondoIndex", mondo_file)

    ols = OlsDescendantResolver() if backend in ("auto", "ols") else None

    def resolve(curie: str) -> Set[str]:
        prefix = normalise_prefix(curie).split(":", 1)[0]
        res = hpo_res if prefix == "HP" else mondo_res if prefix == "MONDO" else None
        if res is not None:
            got = res.descendants(curie)
            if got:
                return got
        if ols is not None:
            return ols.descendants(curie)
        return set()

    return resolve

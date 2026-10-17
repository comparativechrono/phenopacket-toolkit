"""Diff two Documents (after optional normalisation of order/dialect/provenance)."""
from __future__ import annotations

import copy
import json
from typing import List

from ..model.document import Document
from .sort import sort_document

_PROVENANCE_KEYS = {"created", "createdBy"}


def _strip_provenance(obj):
    if isinstance(obj, dict):
        return {k: _strip_provenance(v) for k, v in obj.items()
                if k not in _PROVENANCE_KEYS}
    if isinstance(obj, list):
        return [_strip_provenance(v) for v in obj]
    return obj


def _canonical(doc: Document, ignore) -> dict:
    d = doc
    if "order" in ignore:
        d = sort_document(d)
    raw = copy.deepcopy(d.raw)
    if "provenance" in ignore:
        raw = _strip_provenance(raw)
    return raw


def diff(a: Document, b: Document, *, ignore=("order", "provenance")) -> List[str]:
    """Return a list of difference descriptions ('' -> identical)."""
    ignore = set(ignore)
    ra = _canonical(a, ignore)
    rb = _canonical(b, ignore)
    diffs: List[str] = []
    _walk(ra, rb, "", diffs)
    return diffs


def _walk(a, b, path, out: List[str]) -> None:
    if type(a) is not type(b):
        out.append("{}: type {} != {}".format(path or "<root>",
                                               type(a).__name__, type(b).__name__))
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            p = "{}.{}".format(path, k) if path else k
            if k not in a:
                out.append("{}: only in B".format(p))
            elif k not in b:
                out.append("{}: only in A".format(p))
            else:
                _walk(a[k], b[k], p, out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append("{}: length {} != {}".format(path, len(a), len(b)))
        for i in range(min(len(a), len(b))):
            _walk(a[i], b[i], "{}[{}]".format(path, i), out)
    else:
        if a != b:
            out.append("{}: {!r} != {!r}".format(path, a, b))


def render_diff(diffs: List[str], *, fmt: str = "human") -> str:
    if fmt == "json":
        return json.dumps({"identical": not diffs, "differences": diffs}, indent=2)
    if not diffs:
        return "identical"
    return "\n".join(diffs)

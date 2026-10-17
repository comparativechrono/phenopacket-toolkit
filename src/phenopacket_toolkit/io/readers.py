"""Read phenopacket artifacts into Documents (tolerant reader)."""
from __future__ import annotations

import json
from typing import List, Optional, Union

from ..model.document import Document
from ..model.profile import Dialect, SourceProfile
from . import detect
from .dialects import get_adapter

PathOrText = Union[str, bytes]


def _load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        raise RuntimeError(
            "YAML support needs the optional dependency: pip install 'phenopacket-toolkit[yaml]'")
    return yaml.safe_load(text)


def loads(text: str, *, fmt: str = "json", dialect: Optional[str] = None,
          path: str = "") -> Document:
    """Parse a string into a Document."""
    if fmt == "yaml":
        data = _load_yaml(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object at the top level, got {}".format(type(data).__name__))

    dial = dialect or detect.detect_dialect(data)
    profile = SourceProfile(dialect=dial, fmt=fmt, path=path)
    get_adapter(dial).to_canonical(data, profile)
    return Document(data, profile)


def read(path: str, *, fmt: Optional[str] = None,
         dialect: Optional[str] = None) -> Document:
    """Read a single-document file (json or yaml)."""
    fmt = fmt or detect.detect_format(path)
    if fmt == "jsonl":
        raise ValueError("use read_many() for jsonl input")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return loads(text, fmt=fmt, dialect=dialect, path=path)


def read_many(path: str, *, dialect: Optional[str] = None) -> List[Document]:
    """Read newline-delimited JSON: one Document per non-empty line."""
    docs: List[Document] = []
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            docs.append(loads(line, fmt="json", dialect=dialect,
                              path="{}:{}".format(path, n)))
    return docs

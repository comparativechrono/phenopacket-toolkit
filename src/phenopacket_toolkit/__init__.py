"""phenopacket-toolkit: the samtools/bedtools-style toolkit for GA4GH phenopackets."""
from __future__ import annotations

from .io import read, read_many, to_json_str, to_ped, to_tsv, write, write_many
from .model import Dialect, Document, SourceProfile

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "read", "read_many", "write", "write_many",
    "to_json_str", "to_ped", "to_tsv",
    "Document", "Dialect", "SourceProfile",
]

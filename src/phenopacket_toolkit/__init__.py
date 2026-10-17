"""phenopacket-toolkit: the samtools/bedtools-style toolkit for GA4GH Phenopackets.

From version 0.4 it reads and writes one form of each file, through
pedigree-ga4gh (the GA4GH implementation the lab's pedigree tools share), and
handles GA4GH Pedigrees as well as Phenopackets, Families and Cohorts. The 0.3
"dialects" are gone: files from older versions of studio2ga4gh and
abusua2ga4gh are converted once with ``phenotk upgrade``.
"""
from __future__ import annotations

from .io import LegacyFileError, from_dict, loads, read, read_many, to_json_str, to_ped, to_tsv, write, write_many
from .model import Document, SourceProfile

__version__ = "0.4.0"

__all__ = [
    "__version__", "read", "read_many", "loads", "from_dict", "write", "write_many",
    "to_json_str", "to_ped", "to_tsv", "Document", "SourceProfile", "LegacyFileError",
]

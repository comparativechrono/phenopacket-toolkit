"""Canonical GA4GH dialect: in-memory form == on-disk form. No-op adapters."""
from __future__ import annotations


def to_canonical(data: dict, profile=None) -> dict:
    return data


def from_canonical(data: dict) -> dict:
    return data

"""Builders for well-formed GA4GH Phenopacket v2 sub-objects (camelCase JSON).

These are the rich fields a pedigree conversion never produces: onset/age,
severity, measurements, genomic interpretations (variants), vital-status detail,
subject demographics, external references and files. Every builder returns a
plain dict so it drops straight into the dict-backed model.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .curie import normalise_prefix

_ISO_DUR = re.compile(r"^P(?=\d|T)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T.*)?$")

# common zygosity terms (GENO)
ZYGOSITY = {
    "heterozygous": ("GENO:0000135", "heterozygous"),
    "homozygous": ("GENO:0000136", "homozygous"),
    "hemizygous": ("GENO:0000134", "hemizygous"),
}
# (the same, by id: a zygosity given as its GENO id gets its label)
ZYGOSITY.update({zid.lower(): (zid, zlabel) for zid, zlabel in list(ZYGOSITY.values())})


def ontology_class(id_: str, label: str = "") -> dict:
    return {"id": normalise_prefix(id_), "label": label}


def time_element(value: str, label: str = "") -> dict:
    """Detect the right TimeElement variant from a string.

    * ISO-8601 duration ("P32Y")      -> age
    * CURIE ("HP:0003577")            -> ontologyClass (e.g. an onset term)
    * ISO timestamp ("2021-01-01...") -> timestamp
    """
    v = value.strip()
    if _ISO_DUR.match(v):
        return {"age": {"iso8601duration": v}}
    if ":" in v and not v.endswith("Z") and "T" not in v:
        return {"ontologyClass": ontology_class(v, label)}
    return {"timestamp": v}


def vital_status(status: str, *, cause: Optional[str] = None,
                 cause_label: str = "", survival_days: Optional[int] = None,
                 time_of_death: Optional[str] = None) -> dict:
    out: dict = {"status": status.upper()}
    if cause:
        out["causeOfDeath"] = ontology_class(cause, cause_label)
    if survival_days is not None:
        out["survivalTimeInDays"] = int(survival_days)
    if time_of_death:
        out["timeOfDeath"] = time_element(time_of_death)
    return out


def phenotypic_feature(id_: str, label: str = "", *, excluded: bool = False,
                       onset: Optional[str] = None, onset_label: str = "",
                       severity: Optional[str] = None, severity_label: str = "",
                       modifiers: Optional[List[str]] = None) -> dict:
    out: dict = {"type": ontology_class(id_, label)}
    if excluded:
        out["excluded"] = True
    if onset:
        out["onset"] = time_element(onset, onset_label)
    if severity:
        out["severity"] = ontology_class(severity, severity_label)
    if modifiers:
        out["modifiers"] = [ontology_class(m) for m in modifiers]
    return out


def disease(id_: str, label: str = "", *, excluded: bool = False,
            onset: Optional[str] = None, onset_label: str = "",
            primary_site: Optional[str] = None) -> dict:
    out: dict = {"term": ontology_class(id_, label)}
    if excluded:
        out["excluded"] = True
    if onset:
        out["onset"] = time_element(onset, onset_label)
    if primary_site:
        out["primarySite"] = ontology_class(primary_site)
    return out


def measurement(assay: str, assay_label: str = "", *,
                value: Optional[float] = None, unit: Optional[str] = None,
                unit_label: str = "", categorical: Optional[str] = None,
                categorical_label: str = "", time_observed: Optional[str] = None) -> dict:
    out: dict = {"assay": ontology_class(assay, assay_label)}
    if categorical:
        out["value"] = {"ontologyClass": ontology_class(categorical, categorical_label)}
    elif value is not None:
        q: dict = {"value": float(value)}
        if unit:
            q["unit"] = ontology_class(unit, unit_label)
        out["value"] = {"quantity": q}
    if time_observed:
        out["timeObserved"] = time_element(time_observed)
    return out


def gene_descriptor(value_id: str, symbol: str) -> dict:
    return {"valueId": normalise_prefix(value_id), "symbol": symbol}


def variation_descriptor(*, descriptor_id: str = "var-1",
                         gene_id: Optional[str] = None, gene_symbol: str = "",
                         hgvs: Optional[str] = None,
                         zygosity: Optional[str] = None) -> dict:
    out: dict = {"id": descriptor_id}
    if gene_id:
        out["geneContext"] = gene_descriptor(gene_id, gene_symbol)
    if hgvs:
        syntax = "hgvs.c" if ":c." in hgvs else "hgvs.p" if ":p." in hgvs else "hgvs.g" if ":g." in hgvs else "hgvs"
        out["expressions"] = [{"syntax": syntax, "value": hgvs}]
    if zygosity:
        if zygosity.lower() in ZYGOSITY:
            zid, zlabel = ZYGOSITY[zygosity.lower()]
        else:
            zid, zlabel = zygosity, ""
        out["allelicState"] = ontology_class(zid, zlabel)
    return out


def interpretation(*, interpretation_id: str = "interpretation-1",
                   progress_status: str = "SOLVED",
                   disease_id: Optional[str] = None, disease_label: str = "",
                   subject_id: str = "",
                   interpretation_status: str = "CAUSATIVE",
                   acmg: Optional[str] = None,
                   variation: Optional[dict] = None) -> dict:
    diagnosis: dict = {}
    if disease_id:
        diagnosis["disease"] = ontology_class(disease_id, disease_label)
    if variation is not None:
        gi: dict = {"subjectOrBiosampleId": subject_id,
                    "interpretationStatus": interpretation_status,
                    "variantInterpretation": {"variationDescriptor": variation}}
        if acmg:
            gi["variantInterpretation"]["acmgPathogenicityClassification"] = acmg
        diagnosis["genomicInterpretations"] = [gi]
    return {"id": interpretation_id, "progressStatus": progress_status,
            "diagnosis": diagnosis}


def external_reference(id_: str, reference: str = "", description: str = "") -> dict:
    out: dict = {"id": id_}
    if reference:
        out["reference"] = reference
    if description:
        out["description"] = description
    return out


def file(uri: str, *, individual_to_file: Optional[Dict[str, str]] = None,
         attributes: Optional[Dict[str, str]] = None) -> dict:
    out: dict = {"uri": uri}
    if individual_to_file:
        out["individualToFileIdentifiers"] = dict(individual_to_file)
    if attributes:
        out["fileAttributes"] = dict(attributes)
    return out

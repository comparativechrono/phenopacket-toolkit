"""phenotk command-line interface: one subcommand per verb."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .. import __version__
from ..io import readers, writers
from ..model.profile import Dialect
from ..ops import convert, splitmerge, view
from ..ops import filter as filt
from ..ops import sort as sortop
from ..ops import deidentification as deidentify
from ..ops import diffing as diff
from ..ops import normalisation as norm
from ..ops import statistics as statsop
from ..ops import validation as val
from ..report.render import render_report


def _read(path: str, dialect: Optional[str]) -> "object":
    if path == "-":
        return readers.loads(sys.stdin.read(), dialect=dialect, path="<stdin>")
    return readers.read(path, dialect=dialect)


def _emit(text: str, output: Optional[str]) -> None:
    if output and output != "-":
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


# -- command implementations ----------------------------------------------
def cmd_view(a) -> int:
    doc = _read(a.input, a.dialect)
    _emit(view.render(doc, show_terms=not a.no_terms), a.output)
    return 0


def cmd_validate(a) -> int:
    doc = _read(a.input, a.dialect)
    report = val.validate(doc, level=a.level, online=a.online)
    _emit(render_report(report, fmt=a.format), a.output)
    return 0 if report.ok else 1


def cmd_stats(a) -> int:
    doc = _read(a.input, a.dialect)
    res = statsop.stats(doc)
    _emit(statsop.render_stats(res, fmt=a.format), a.output)
    return 0


def cmd_normalise(a) -> int:
    doc = _read(a.input, a.dialect)
    mapping = json.load(open(a.mapping)) if a.mapping else None
    if isinstance(mapping, dict) and "resolved" in mapping:
        mapping = mapping["resolved"]      # accept a decision-log file directly
    out, log = norm.normalise(
        doc, terms=not a.structure_only, structure=not a.terms_only,
        threshold=a.threshold, backend=a.backend, mapping=mapping,
        hpo_file=a.hpo_file, mondo_file=a.mondo_file,
        use_ontology=not a.no_online)
    _write_doc(out, a)
    if a.log:
        with open(a.log, "w", encoding="utf-8") as fh:
            fh.write(log.to_json())
    if not a.structure_only:
        to_stdout = not (a.output or a.in_place)
        sys.stderr.write(log.summary(to_stdout=to_stdout) + "\n")
    return 0


def cmd_filter(a) -> int:
    doc = _read(a.input, a.dialect)
    resolver = None
    if a.include_descendants:
        from ..ontology.hierarchy import make_resolver
        resolver = make_resolver(backend=a.backend, hpo_file=a.hpo_file,
                                 mondo_file=a.mondo_file)
    out = filt.filter_document(
        doc, terms=a.term or None, include_descendants=a.include_descendants,
        descendant_resolver=resolver,
        observed_only=a.observed, excluded_only=a.excluded,
        affected_only=a.affected, proband_only=a.proband_only, sex=a.sex,
        id_list=_read_id_list(a.id_list), invert=a.invert,
        prune_pedigree=a.prune_pedigree)
    _write_doc(out, a)
    return 0


def cmd_deidentify(a) -> int:
    doc = _read(a.input, a.dialect)
    res = deidentify.deidentify(
        doc, remap_ids=(None if a.keep_ids else a.remap_ids), salt=a.salt,
        drop_dob=not a.keep_dob, bin_age=a.bin_age, drop_names=not a.keep_names,
        drop_provenance=a.drop_provenance)
    _write_doc(res.document, a)
    if a.keyfile and res.crosswalk:
        with open(a.keyfile, "w", encoding="utf-8") as fh:
            json.dump(res.crosswalk, fh, indent=2)
    for w in res.warnings:
        sys.stderr.write("warning: {}\n".format(w))
    return 0


def cmd_convert(a) -> int:
    doc = _read(a.input, a.dialect)
    if a.to in ("yaml", "jsonl"):
        if not a.output or a.output == "-":
            sys.stderr.write("convert --to {} needs -o FILE\n".format(a.to)); return 2
        if a.to == "jsonl":
            writers.write_many([doc], a.output, dialect=a.to_dialect)
        else:
            writers.write(doc, a.output, dialect=a.to_dialect, fmt="yaml")
        return 0
    _emit(convert.to_format(doc, a.to, dialect=a.to_dialect), a.output)
    return 0


def cmd_sort(a) -> int:
    doc = _read(a.input, a.dialect)
    _write_doc(sortop.sort_document(doc), a)
    return 0


def cmd_diff(a) -> int:
    da = _read(a.a, a.dialect)
    db = _read(a.b, a.dialect)
    ignore = [] if a.strict else ["order", "provenance", "dialect"]
    diffs = diff.diff(da, db, ignore=ignore)
    _emit(diff.render_diff(diffs, fmt=a.format), a.output)
    return 0 if not diffs else 1


def cmd_split(a) -> int:
    doc = _read(a.input, a.dialect)
    docs = splitmerge.split(doc, affected_only=a.affected_only)
    import os
    os.makedirs(a.out_dir, exist_ok=True)
    for d in docs:
        sid = (d.proband().subject.id if d.proband() else "unknown")
        path = os.path.join(a.out_dir, "{}.json".format(sid))
        writers.write(d, path, dialect=a.to_dialect)
    sys.stderr.write("wrote {} phenopacket(s) to {}\n".format(len(docs), a.out_dir))
    return 0


def cmd_merge(a) -> int:
    docs = [_read(p, a.dialect) for p in a.inputs]
    out = splitmerge.merge(docs, into=a.into, cohort_id=a.id)
    _write_doc(out, a)
    return 0


def cmd_ped(a) -> int:
    doc = _read(a.input, a.dialect)
    _emit(writers.to_ped(doc), a.output)
    return 0


def _parse_curie_label(spec):
    if spec is None:
        return None, ""
    if "=" in spec:
        cid, label = spec.split("=", 1)
        return cid.strip(), label.strip()
    return spec.strip(), ""


def _parse_pathval(spec):
    if "=" not in spec:
        raise ValueError("expected PATH=JSON, got {!r}".format(spec))
    path, val = spec.split("=", 1)
    try:
        value = json.loads(val)
    except json.JSONDecodeError:
        value = val           # treat a bare token as a string
    return path.strip(), value


def cmd_add(a) -> int:
    from ..ops import annotate
    from ..model import builders as B
    doc = _read(a.input, a.dialect)

    phenotypes = []
    for spec in (a.phenotype or []):
        cid, label = _parse_curie_label(spec)
        kw = {"id_": cid, "label": label, "excluded": a.excluded}
        if a.onset:
            kw["onset"] = a.onset
        if a.severity:
            sid, slabel = _parse_curie_label(a.severity)
            kw["severity"] = sid; kw["severity_label"] = slabel
        phenotypes.append(kw)

    diseases = []
    for spec in (a.disease or []):
        cid, label = _parse_curie_label(spec)
        kw = {"id_": cid, "label": label}
        if a.onset:
            kw["onset"] = a.onset
        diseases.append(kw)

    measurements = [json.loads(m) for m in (a.measurement_json or [])]

    interpretations = None
    if a.variant or a.diagnosis:
        var = None
        if a.variant:
            gid, gsym = _parse_curie_label(a.gene) if a.gene else (None, "")
            var = B.variation_descriptor(gene_id=gid, gene_symbol=gsym,
                                         hgvs=a.hgvs, zygosity=a.zygosity)
        did, dlabel = _parse_curie_label(a.diagnosis) if a.diagnosis else (None, "")
        # subject id filled per-target below via patch is awkward; use proband id
        subj = doc.proband().subject.id if doc.proband() else ""
        interpretations = [B.interpretation(
            progress_status=a.progress_status, disease_id=did, disease_label=dlabel,
            subject_id=subj, acmg=a.acmg, variation=var)]

    external_references = []
    for spec in (a.external_ref or []):
        head, _, desc = spec.partition(";;")
        rid, _, ref = head.partition("=")
        external_references.append(B.external_reference(rid.strip(), ref.strip(), desc.strip()))

    vital = None
    if a.vital_status:
        cid, clabel = _parse_curie_label(a.cause) if a.cause else (None, "")
        vital = B.vital_status(a.vital_status, cause=cid, cause_label=clabel,
                               survival_days=a.survival_days, time_of_death=a.time_of_death)

    subject_fields = {}
    if a.birth_date:
        subject_fields["dateOfBirth"] = a.birth_date
    if a.age:
        subject_fields["timeAtLastEncounter"] = B.time_element(a.age)
    if a.karyotypic_sex:
        subject_fields["karyotypicSex"] = a.karyotypic_sex
    if a.gender:
        gid, glabel = _parse_curie_label(a.gender)
        subject_fields["gender"] = B.ontology_class(gid, glabel)
    if a.taxon:
        tid, tlabel = _parse_curie_label(a.taxon)
        subject_fields["taxonomy"] = B.ontology_class(tid, tlabel)

    patch = json.load(open(a.from_json)) if a.from_json else None

    out = annotate.add(
        doc, a.target,
        phenotypes=phenotypes or None, diseases=diseases or None,
        measurements=measurements or None, interpretations=interpretations,
        external_references=external_references or None,
        vital_status=vital, subject_fields=subject_fields or None,
        set_paths=[_parse_pathval(s) for s in (a.set or [])],
        merge_paths=[_parse_pathval(s) for s in (a.merge or [])],
        append_paths=[_parse_pathval(s) for s in (a.append or [])],
        patch=patch)
    _write_doc(out, a)
    return 0


# -- shared helpers --------------------------------------------------------
def _write_doc(doc, a) -> None:
    text = writers.to_json_str(doc, dialect=getattr(a, "to_dialect", Dialect.GA4GH))
    out = getattr(a, "output", None)
    if getattr(a, "in_place", False) and a.input != "-":
        out = a.input
    _emit(text, out)


def _read_id_list(path: Optional[str]) -> Optional[List[str]]:
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def _read_id_list_safe(path):
    return _read_id_list(path)


# -- argument parser -------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phenotk",
                                description="samtools/bedtools-style toolkit for GA4GH phenopackets")
    p.add_argument("--version", action="version", version="phenotk " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, output=True, dialect_in=True, writes=False):
        if dialect_in:
            sp.add_argument("--dialect", choices=Dialect.ALL, default=None,
                            help="force input dialect (default: auto-detect)")
        if output:
            sp.add_argument("-o", "--output", default=None, help="output file (default: stdout)")
        if writes:
            sp.add_argument("--to-dialect", choices=Dialect.ALL, default=Dialect.GA4GH,
                            help="output dialect (default: ga4gh)")
            sp.add_argument("--in-place", action="store_true", help="overwrite the input file")

    sp = sub.add_parser("view", help="render a readable table")
    sp.add_argument("input"); sp.add_argument("--no-terms", action="store_true")
    common(sp); sp.set_defaults(func=cmd_view)

    sp = sub.add_parser("validate", help="layered conformance + lint")
    sp.add_argument("input")
    sp.add_argument("--level", choices=["syntactic", "structural", "reference", "ontology", "lint"],
                    default="lint")
    sp.add_argument("--online", action="store_true")
    sp.add_argument("--format", choices=["human", "json"], default="human")
    common(sp); sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("stats", help="counts and term frequency")
    sp.add_argument("input"); sp.add_argument("--format", choices=["human", "json"], default="human")
    common(sp); sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("normalise", help="fill term ids + tidy structure")
    sp.add_argument("input")
    sp.add_argument("--terms-only", action="store_true")
    sp.add_argument("--structure-only", action="store_true")
    sp.add_argument("--threshold", type=float, default=0.9)
    sp.add_argument("--backend", choices=["auto", "ols", "local"], default="auto")
    sp.add_argument("--mapping", default=None, help="label->id JSON (or a decision-log file)")
    sp.add_argument("--hpo-file", default=None); sp.add_argument("--mondo-file", default=None)
    sp.add_argument("--no-online", action="store_true",
                    help="do not call hponorm/mondonorm; mapping-only")
    sp.add_argument("--log", default=None, help="write a decision log JSON here")
    common(sp, writes=True); sp.set_defaults(func=cmd_normalise)

    sp = sub.add_parser("filter", help="subset by term / individual / data presence")
    sp.add_argument("input")
    sp.add_argument("--term", action="append", help="CURIE to keep (repeatable)")
    sp.add_argument("--include-descendants", action="store_true")
    sp.add_argument("--backend", choices=["auto", "obo", "ols"], default="auto",
                    help="hierarchy source for --include-descendants")
    sp.add_argument("--hpo-file", default=None, help="hp.obo for HP descendants")
    sp.add_argument("--mondo-file", default=None, help="mondo.obo for MONDO descendants")
    sp.add_argument("--observed", action="store_true"); sp.add_argument("--excluded", action="store_true")
    sp.add_argument("--affected", action="store_true"); sp.add_argument("--proband-only", action="store_true")
    sp.add_argument("--sex", default=None); sp.add_argument("--id-list", default=None)
    sp.add_argument("--invert", action="store_true"); sp.add_argument("--prune-pedigree", action="store_true")
    common(sp, writes=True); sp.set_defaults(func=cmd_filter)

    sp = sub.add_parser("deidentify", help="scrub PII, remap ids consistently")
    sp.add_argument("input")
    sp.add_argument("--remap-ids", choices=["seq", "hash"], default="seq")
    sp.add_argument("--keep-ids", action="store_true"); sp.add_argument("--salt", default=None)
    sp.add_argument("--keep-dob", action="store_true"); sp.add_argument("--bin-age", default=None)
    sp.add_argument("--keep-names", action="store_true"); sp.add_argument("--drop-provenance", action="store_true")
    sp.add_argument("--keyfile", default=None, help="write the old->new id crosswalk here")
    common(sp, writes=True); sp.set_defaults(func=cmd_deidentify)

    sp = sub.add_parser("convert", help="dialect/format conversion")
    sp.add_argument("input")
    sp.add_argument("--to", choices=["json", "yaml", "jsonl", "ped", "tsv"], default="json")
    common(sp, writes=True); sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("sort", help="canonical ordering")
    sp.add_argument("input"); common(sp, writes=True); sp.set_defaults(func=cmd_sort)

    sp = sub.add_parser("diff", help="compare two documents")
    sp.add_argument("a"); sp.add_argument("b")
    sp.add_argument("--strict", action="store_true", help="do not ignore order/provenance/dialect")
    sp.add_argument("--format", choices=["human", "json"], default="human")
    common(sp); sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("split", help="explode a family into per-individual files")
    sp.add_argument("input"); sp.add_argument("--out-dir", required=True)
    sp.add_argument("--affected-only", action="store_true")
    sp.add_argument("--to-dialect", choices=Dialect.ALL, default=Dialect.GA4GH)
    sp.add_argument("--dialect", choices=Dialect.ALL, default=None)
    sp.set_defaults(func=cmd_split)

    sp = sub.add_parser("merge", help="combine documents into a cohort/family")
    sp.add_argument("inputs", nargs="+")
    sp.add_argument("--into", choices=["cohort", "family"], default="cohort")
    sp.add_argument("--id", default="cohort")
    common(sp, writes=True); sp.set_defaults(func=cmd_merge)

    sp = sub.add_parser("ped", help="export a PED file")
    sp.add_argument("input"); common(sp); sp.set_defaults(func=cmd_ped)

    sp = sub.add_parser("add", help="add rich fields to selected individuals")
    sp.add_argument("input")
    sp.add_argument("--target", default="proband",
                    help="proband | all | affected | unaffected | <subject-id>")
    sp.add_argument("--phenotype", action="append", metavar="CURIE[=Label]")
    sp.add_argument("--disease", action="append", metavar="CURIE[=Label]")
    sp.add_argument("--onset", default=None, help="ISO age (P10Y), onset CURIE, or timestamp")
    sp.add_argument("--excluded", action="store_true", help="mark added phenotypes as excluded")
    sp.add_argument("--severity", default=None, metavar="CURIE[=Label]")
    sp.add_argument("--measurement-json", action="append",
                    help="JSON of builder kwargs, e.g. '{\"assay\":\"LOINC:8867-4\",\"value\":480,\"unit\":\"UCUM:ms\"}'")
    sp.add_argument("--vital-status", default=None, choices=["ALIVE", "DECEASED", "UNKNOWN_STATUS"])
    sp.add_argument("--cause", default=None, metavar="CURIE[=Label]")
    sp.add_argument("--survival-days", type=int, default=None)
    sp.add_argument("--time-of-death", default=None)
    sp.add_argument("--birth-date", default=None); sp.add_argument("--age", default=None)
    sp.add_argument("--karyotypic-sex", default=None)
    sp.add_argument("--gender", default=None, metavar="CURIE[=Label]")
    sp.add_argument("--taxon", default=None, metavar="CURIE[=Label]")
    sp.add_argument("--variant", action="store_true", help="attach a genomic interpretation")
    sp.add_argument("--gene", default=None, metavar="HGNC:xxx=SYMBOL")
    sp.add_argument("--hgvs", default=None); sp.add_argument("--zygosity", default=None)
    sp.add_argument("--acmg", default=None)
    sp.add_argument("--diagnosis", default=None, metavar="CURIE[=Label]")
    sp.add_argument("--progress-status", default="SOLVED")
    sp.add_argument("--external-ref", action="append", metavar="ID[=ref][;;desc]")
    sp.add_argument("--set", action="append", metavar="PATH=JSON")
    sp.add_argument("--merge", action="append", metavar="PATH=JSON")
    sp.add_argument("--append", action="append", metavar="PATH=JSON")
    sp.add_argument("--from-json", default=None, help="deep-merge a JSON patch into each target")
    common(sp, writes=True); sp.set_defaults(func=cmd_add)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        sys.stderr.write("error: {}\n".format(e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

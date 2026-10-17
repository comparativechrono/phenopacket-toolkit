# phenopacket-toolkit (`phenotk`)

A **samtools/bedtools-style** command-line toolkit and Python library for working
with [GA4GH Phenopackets](https://phenopacket-schema.readthedocs.io/) and Family
JSON files. One verb per subcommand, composable over pipes, structured output,
CI-friendly exit codes.

It reads files produced by different tools (including the `abusua2ga4gh` and
`studio2ga4gh` dialects) **and** anyone else's GA4GH-compliant phenopackets,
normalises them, slices them down to chosen phenotypes, de-identifies them,
validates them, and converts between structural variants.

- **Zero-dependency core.** `read/write/validate/view/stats/filter/deidentify/
  diff/sort/convert/split/merge/ped` need nothing beyond the standard library.
- **Tolerant reader, configurable writer, lossless round-trip.** Unknown fields
  are preserved; dialect quirks are reconciled on read and restored on write.
- **No-guess ontology contract.** Ontology IDs are only ever filled by the
  `normalise` step, under an explicit auto-accept policy.

## Install

```bash
pip install phenopacket-toolkit                 # zero-dependency core
pip install 'phenopacket-toolkit[normalise]'    # + hponorm / mondonorm
pip install 'phenopacket-toolkit[all]'          # + rapidfuzz, PyYAML, protobuf validation
```

Requires Python >= 3.9.

## Quick start (CLI)

```bash
phenotk view family.json                       # readable table
phenotk validate family.json --level reference # layered checks; non-zero exit on error
phenotk stats family.json --format json        # counts + term frequency

# fill ontology ids from a curated mapping, leaving anything unmatched empty
phenotk normalise family.json --no-online \
    --mapping labels.json --log decisions.json -o family.norm.json

# cut a family down to a phenotype, expanding to descendant terms via an OBO file
phenotk filter family.json --term HP:0001626 --include-descendants \
    --backend obo --hpo-file hp.obo -o subset.json

# enrich the proband with data a pedigree never carries: onset, a variant, demographics
phenotk add family.json --target proband \
    --phenotype "HP:0001657=Prolonged QT interval" --onset P14Y --severity "HP:0012828=Severe" \
    --variant --gene "HGNC:6294=KCNQ1" --hgvs "NM_000218.3:c.569G>A" \
        --zygosity heterozygous --acmg PATHOGENIC --diagnosis "MONDO:0011382=sickle cell disease" \
    --karyotypic-sex XY --age P14Y --external-ref "PMID:31479590;;index case" \
    -o enriched.json

# de-identify: drop DOB, remap every id consistently, keep a reversible crosswalk
phenotk deidentify family.json --remap-ids seq --keyfile key.json -o deid.json

phenotk convert family.json --to ped           # 6-column PED
phenotk convert family.json --to tsv           # one row per (individual, term)
phenotk diff a.json b.json                      # structural+semantic diff
phenotk split family.json --out-dir out/ --affected-only
```

Most commands read `-` for stdin and write stdout, so they compose:

```bash
cat family.json | phenotk filter - --affected | phenotk deidentify - -o clean.json
```

## Quick start (library)

```python
from phenopacket_toolkit import read, write
from phenopacket_toolkit.ops import normalise, filter_document, deidentify, validate

doc = read("family.json")                       # auto-detects format + dialect

doc, log = normalise(doc, mapping={"diabetes": "MONDO:0005015"}, use_ontology=False)
doc = filter_document(doc, terms=["MONDO:0005015"])
result = deidentify(doc, drop_dob=True, remap_ids="seq")

report = validate(result.document, level="reference")
if report.ok:
    write(result.document, "clean.json", dialect="ga4gh")
```

## Dialects

| Dialect  | Source                         | Reconciled on read                              |
|----------|--------------------------------|-------------------------------------------------|
| `ga4gh`  | spec-compliant                 | (canonical)                                     |
| `abusua` | `abusua2ga4gh` `*.family.json` | `vital_status` -> `vitalStatus`                 |
| `studio` | `studio2ga4gh` `*_phenopackets.json` | Family `metaData` inherited into each phenopacket |

Choose the output dialect with `--to-dialect` (CLI) or `dialect=` (library);
`--to-dialect preserve` re-emits in the source dialect. New dialects can be
registered without touching the core via
`phenopacket_toolkit.io.dialects.register`.

## Verbs

`view`, `validate`, `normalise`, `filter`, `add`, `deidentify`, `convert`,
`merge`, `split`, `stats`, `diff`, `sort`, `ped`. Run `phenotk <verb> --help`
for options.

## Adding fields a pedigree never carries

A pedigree conversion gives you structure, sex, affected status and bare
phenotype/disease labels. `add` lets you layer on the richer Phenopacket v2
content, targeting the `proband`, `all`, `affected`/`unaffected`, or a specific
subject id:

- **Age / onset** on phenotypes and diseases (`--onset P14Y`, an onset CURIE, or
  a timestamp), plus **severity** and **excluded** status.
- **Genomic interpretations** — a variant with gene context, HGVS expression,
  zygosity (GENO) and ACMG pathogenicity, wrapped in a diagnosis.
- **Measurements** — quantitative or categorical lab values (`--measurement-json`).
- **Vital status detail** — `DECEASED`, cause of death, survival time.
- **Subject demographics** — `dateOfBirth`, age (`timeAtLastEncounter`),
  `karyotypicSex`, `gender`, `taxonomy`.
- **External references** (PMIDs etc.) and **files** (e.g. a linked VCF).
- **Anything else** via generic `--set PATH=JSON`, `--merge`, `--append`, or a
  whole-object `--from-json PATCH`.

In the library these are typed builders in `phenopacket_toolkit.model.builders`
plus `phenopacket_toolkit.ops.add`.

## Hierarchy-aware filtering

`filter --include-descendants` keeps a term *and any of its subclasses*. The
descendant set is resolved by `--backend`: `obo` parses an `hp.obo` / `mondo.obo`
file (`--hpo-file` / `--mondo-file`, fully offline), `ols` queries the EBI
Ontology Lookup Service, and `auto` tries a local source then falls back to OLS.

## Normalisation and ontologies

`normalise` fills empty term ids in this order: an explicit `--mapping` (label ->
CURIE) always wins; remaining empties are resolved via `hponorm` (phenotypes) and
`mondonorm` (diseases) when the `[normalise]` extra is installed; anything that
does not clear the score `--threshold` (default 0.9) is left empty and recorded
in the decision log. `--structure` additionally canonicalises CURIE prefixes,
de-duplicates terms, and rebuilds `metaData.resources` from the ontologies in use.

## Development

```bash
pip install -e . --no-build-isolation
python run_tests.py tests/test_toolkit.py    # offline runner (no pytest needed)
pytest                                       # if pytest is available
```

The test suite is driven by real example families in `tests/data/` and checks
round-trip fidelity, cross-dialect equivalence, pedigree-graph validation,
graph-consistent de-identification, and idempotent no-guess normalisation.

## License

MIT.

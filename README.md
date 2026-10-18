# phenopacket-toolkit (`phenotk`)

A **samtools/bedtools-style** command-line toolkit and Python library for
[GA4GH Phenopackets](https://phenopacket-schema.readthedocs.io/) and GA4GH
pedigrees. One verb per subcommand, composable over pipes, structured output,
exit codes you can use in scripts and CI.

It views, checks, normalises, filters, de-identifies, enriches and converts
Phenopackets, Phenopackets Families and Cohorts, and **GA4GH Pedigrees**. Since
0.4 it reads and writes them through
[pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh), the one
GA4GH implementation that studio2ga4gh, ga4gh2studio and the Pedigree workbench
also use, so all of them agree on a single, standard form.

- **One form.** A GA4GH Pedigree is the Phenopackets form of the published
  standard (every individual a Phenopacket v2, relationships coded with KIN);
  Families, Phenopackets and Cohorts follow the Phenopackets v2 schema. Files
  from older tools are recognised and converted once with `phenotk upgrade`.
- **Small core.** Everything except ontology look-ups needs only pedigree-ga4gh,
  which itself needs nothing beyond the standard library.
- **No guessing.** Ontology ids are only ever filled in by `normalise`, from a
  mapping you give it or a look-up that finds the name as a term's label or
  synonym, and every decision is logged.

## Install

```bash
pip install phenopacket-toolkit                 # the core
pip install 'phenopacket-toolkit[normalise]'    # + hponorm and mondonorm, for looking terms up
pip install 'phenopacket-toolkit[all]'          # + rapidfuzz (faster matching) and PyYAML
```

Requires Python 3.9 or later.

## Quick start (command line)

```bash
phenotk view family.json                        # a readable table
phenotk validate family.json                    # Phenopackets v2 and the GA4GH Pedigree; exit 1 on errors
phenotk stats family.json --format json         # counts and term frequency

# a file from studio2ga4gh 0.3 or abusua2ga4gh 0.2: convert it once
phenotk upgrade old_phenopackets.json -o family.json

# fill empty term ids from a curated mapping, leaving anything unmatched empty
phenotk normalise family.json --no-online \
    --mapping labels.json --log decisions.json -o family.norm.json

# cut a family down to a phenotype, including its more specific terms, from an OBO file
phenotk filter family.json --term HP:0001626 --include-descendants \
    --backend obo --hpo-file hp.obo -o subset.json

# add what a pedigree never carries: onset, severity, a variant, demographics
phenotk add family.json --target proband \
    --phenotype "HP:0001657=Prolonged QT interval" --onset P14Y --severity "HP:0012828=Severe" \
    --variant --gene "HGNC:6294=KCNQ1" --hgvs "NM_000218.3:c.569G>A" \
        --zygosity heterozygous --acmg PATHOGENIC --diagnosis "MONDO:0100316=long QT syndrome 1" \
    --karyotypic-sex XY --age P14Y --external-ref "PMID:31479590;;index case" \
    -o enriched.json

# de-identify: drop dates of birth, remap every id consistently, keep a crosswalk
phenotk deidentify family.json --remap-ids seq --keyfile key.json -o deid.json

phenotk convert pedigree.json --to family       # GA4GH Pedigree -> Phenopackets Family
phenotk convert family.json --to pedigree       # and back
phenotk convert family.json --to ped            # 6-column PED
phenotk convert family.json --to tsv            # one row per (individual, term)
phenotk diff a.json b.json                      # structural and semantic differences
phenotk split family.json --out-dir out/ --affected-only
```

Most commands read `-` for standard input and write to standard output, so
they compose:

```bash
cat family.json | phenotk filter - --affected | phenotk deidentify - -o clean.json
```

## Quick start (library)

```python
from phenopacket_toolkit import read, write
from phenopacket_toolkit.ops import normalise, filter_document, deidentify, validate

doc = read("family.json")                 # a Family, Phenopacket, Cohort or GA4GH Pedigree

doc, log = normalise(doc, mapping={"diabetes": "MONDO:0005015"}, use_ontology=False)
doc = filter_document(doc, terms=["MONDO:0005015"])
result = deidentify(doc, drop_dob=True, remap_ids="seq")

report = validate(result.document)
if report.ok:
    write(result.document, "clean.json")
```

## Verbs

`view`, `validate`, `stats`, `normalise`, `filter`, `deidentify`, `convert`,
`upgrade`, `sort`, `diff`, `split`, `merge`, `ped`, `add`. Run
`phenotk <verb> --help` for the options.

## Older files

Version 0.3 had "dialects" so that it could read the GA4GH files of
studio2ga4gh 0.3 and abusua2ga4gh 0.2. Neither was in the standard's form, and
reading both kept them alive. 0.4 reads one form: an older file is refused with
a message, and `phenotk upgrade FILE -o NEW.json` rewrites it once, listing
every change and what still needs a person (usually conditions without an
ontology term). Files in the form of the draft of version 1 of the GA4GH
Pedigree Standard, which is not yet approved, are recognised and refused with
a message saying so.

## Adding fields a pedigree never carries

A pedigree conversion gives you structure, sex, affected status and the
conditions. `add` lets you layer on the richer Phenopacket v2 content,
targeting the `proband`, `all`, `affected` or `unaffected` people, or one
subject id:

- **Age / onset** on phenotypes and diseases (`--onset P14Y`, an onset CURIE, or
  a timestamp), plus **severity** and **excluded** status.
- **Genomic interpretations** — a variant with gene context, HGVS expression,
  zygosity (GENO) and ACMG pathogenicity, in a diagnosis of the disease you give
  (`--diagnosis` is required with `--variant`, since a diagnosis needs one).
- **Measurements** — quantitative or categorical lab values (`--measurement-json`).
- **Vital status detail** — `DECEASED`, cause of death, survival time.
- **Subject demographics** — `dateOfBirth`, age (`timeAtLastEncounter`),
  `karyotypicSex`, `gender`, `taxonomy`.
- **External references** (PMIDs and so on) and **files** (a linked VCF, say).
- **Anything else** via `--set PATH=JSON`, `--merge`, `--append`, or a
  whole-object `--from-json PATCH`.

Every ontology the added terms use is declared in `metaData`, so the result
stays valid. In the library these are the builders in
`phenopacket_toolkit.model.builders` and `phenopacket_toolkit.ops.add`.

## Hierarchy-aware filtering

`filter --include-descendants` keeps a term *and any of its more specific
terms*. They come from `--backend`: `obo` reads an `hp.obo` / `mondo.obo` file
(`--hpo-file` / `--mondo-file`, fully offline), `ols` asks EBI's Ontology
Lookup Service, and `auto` tries a local file and falls back to OLS. Filtering
a Family never leaves it without its proband, and the pedigree keeps everyone
the filters did not take out.

## Normalisation and ontologies

`normalise` fills empty term ids in this order: an explicit `--mapping` (label
-> CURIE, matched without regard to case) always wins; the rest are looked up
with `hponorm` (phenotypes) and `mondonorm` (diseases) when the `[normalise]`
extra is installed. By default a term they find is accepted only if the name is
its label or one of its synonyms, ignoring case and punctuation. Their scores,
from 0 to 100, are divided by 100: the label scores 1, a synonym 0.98 and
anything else at most 0.97, so `--threshold` (the lowest score accepted,
by default 0.98) admits only the term's own names. Anything else is left empty
and recorded in the decision log.

You can lower the threshold to accept names that are only close, but each of
those is a guess for a person to check, because names spelt almost alike can
mean opposite things: "Maternal hypothyroidism" is not HP:0034778 *Maternal
hyperthyroidism*, and "Essential hypotension" is not MONDO:0001134 *essential
hypertension*, although version 1.0 of hponorm and mondonorm scores those
pairs 93.6 and 93 out of 100. The decision log notes every term accepted
below 0.98 and asks for it to be checked. Version 1.1 of hponorm and
mondonorm scores names like these far lower, as it does names of a different
type or number, but its close matches are still guesses. Version 1.0 does not
keep its highest scores for exact matches, so with 1.0 a result counts as
exact only if the name is its label or the synonym it was found by; its
results from OLS come without their synonyms, so for those only the label
counts.

The structure step then puts each term where it belongs (an HPO term among the
phenotypic features, a Mondo, OMIM or Orphanet term among the diseases),
removes duplicates, and declares every ontology in use in
`metaData.resources`, with its release when it is known.

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests use fictional families in `tests/data` and small sample ontologies,
so they never go online.

## Licence

MIT.

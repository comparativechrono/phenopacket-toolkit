# Changelog

## 0.4.0

phenopacket-toolkit now reads and writes GA4GH files through
[pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh), the one
GA4GH implementation shared by the lab's pedigree tools, and depends on it.

**One form.** The 0.3 "dialects", which let it read the GA4GH files of
studio2ga4gh 0.3 and abusua2ga4gh 0.2, are gone: neither was in the
standard's form, and reading both kept them alive. An older file is refused
with a message, and the new `phenotk upgrade` rewrites it once, listing every
change and what is left to do. GA4GH Pedigrees (the Phenopackets form of the
published standard) are handled as documents of their own: view, stats,
filter, de-identify, sort, split, merge, PED export, and `convert --to family`
and `--to pedigree` between them and Families. Files in the form of the draft
of version 1 of the standard are recognised and refused with a message.

**Validation** is pedigree-ga4gh's: the checks of phenopacket-tools' JSON
schemas and MetaDataValidator, and the pedigree's own (KIN terms, people named
in relationships, parents' sexes, loops of ancestry), all at once.

**Fixed:**

- `normalise` with EBI's Ontology Lookup Service accepted the first result for
  every name, however poor the match: hponorm's and mondonorm's OLS clients
  score results by their rank (100, 96, 92 …), so the first always looked
  like an exact match. Results are now scored by how closely their label
  matches the name, so the threshold means what it says.
- `normalise` accepts only exact matches unless told otherwise: a looked-up
  term is filled in only if the name is its label or one of its synonyms,
  ignoring case and punctuation. The default `--threshold` is now 0.98. At
  0.9 it let through names spelt almost alike that mean something else:
  "Maternal hypothyroidism" was filled with HP:0034778 *Maternal
  hyperthyroidism*, which hponorm 1.0 scores 93.6 for it, and "Essential
  hypotension" with MONDO:0001134 *essential hypertension*, which mondonorm
  1.0 scores 93. A lower threshold still accepts close names, but they are
  guesses for a person to check, and the decision log now lists each one.
  With hponorm and mondonorm 1.0, whose local search can score a long name
  with one character changed as highly as an exact match, a result counts as
  exact only if the name is its label or the synonym it was found by.
- `normalise` records the release of each ontology used (from an OBO file,
  OLS, or a terms file whose entries carry a `version`), and moves a term to
  where its ontology belongs: an HPO term written as a disease becomes a
  phenotypic feature, and a Mondo, OMIM or Orphanet term written as a
  phenotypic feature becomes a disease.
- `merge` gave everyone in a merged Family no parents, and kept only the first
  input's metaData, losing the other inputs' ontology releases. The Family's
  pedigree now comes from the Families and GA4GH Pedigrees among the inputs,
  the metaData declares every ontology they declare, and repeated ids are
  handled (in a Family the first Phenopacket for a person is kept; in a Cohort
  later ones are renamed after their file's id). Both are reported.
- `filter --prune-pedigree` on a Family kept in its pedigree only the people
  with a Phenopacket, so the relatives with nothing recorded went too and the
  file was invalid. Only the people the filters left out are removed now.
  Filters that would leave a Family without its proband are refused.
- `deidentify --drop-provenance` removed `created` and `createdBy`, which
  metaData requires. They are now replaced by the de-identification's own.
  De-identifying a GA4GH Pedigree also replaces the old ids in its narrative,
  with a warning that the narrative is free text to read before sharing.
- `add` did not declare a new ontology in `metaData`, gave every variant the
  proband's id whoever it was added to, wrote a diagnosis without a disease
  when `--diagnosis` was left out (now refused, since a diagnosis needs one),
  and gave a zygosity given as a GENO id no label. All four are fixed.
- `filter --include-descendants` would have downloaded the whole of Mondo
  (or the HPO) once hponorm and mondonorm 1.1 are installed: it tried their
  ontology index, which version 1.0 did not make available and which, given
  no file, downloads the ontology. It now uses an index only if it can list a
  term's descendants (neither can yet) and never downloads one.
- With hponorm and mondonorm 1.1, a name that OLS gave no answer for is noted
  in `normalise`'s decision log as such, instead of looking like a name with no
  match.

**Also:** 0.3's `--dialect`, `--to-dialect`, and `validate --level` and
`--online`, are still accepted so that old commands run, and are ignored with
a note; `python -m phenopacket_toolkit` runs `phenotk`; the `validate` extra
installs nothing more (validation needs only pedigree-ga4gh); and the tests
now come with their data, use small sample ontologies, and never go online.

## 0.3.0

Released on PyPI on 2 June 2026.

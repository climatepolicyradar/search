# Lucene Linguistics

Vespa's
[Lucene Linguistics](https://docs.vespa.ai/en/linguistics/lucene-linguistics.html)
replaces the default English Porter stemmer with configurable per-field analyzer
profiles powered by Apache Lucene.

## Setup

- **Profiles** are defined in `services.xml`. These are pipelines of tokenizers,
  analysers, stemmers etc. (or the lack of those, for a specific pipeline)
- **Setting language in every query.** `"model.language": "en"` is needed in
  every Vespa query so that Vespa applies the correct Lucene profile at query
  time.

## Constraints & gotchas

- **All fields in a single fieldset must share the same linguistics profile.**
  If you want a field to use a different profile, it must be in a separate
  fieldset. You can use `userInput` on multiple fields in a query by setting
  `defaultIndex`, e.g.:

  ```sql
  select * from documents where
  {defaultIndex: "default"}userInput(@query)
  or {defaultIndex: "labels_fieldset"}userInput(@query)
  ```

## Features

### Stemming modes

- **`stemming: multiple`** — indexes both the original token and all stems
  produced by the analyzer. Used on `title` and `description` so that searches
  match both "running" and "run".
- **`stemming: none`** — disables Vespa's built-in Porter stemmer, leaving only
  the Lucene profile in control. Used on `labels_value` and `concepts_value` to
  prevent unwanted stemming of controlled vocabulary.

### Stop words

The stopwords file lives at `vespa/app/lucene-linguistics/en/stopwords.txt`. The
`configDir` setting in `services.xml` points Lucene to this directory so the
stopwords filter can find the file.

To add or remove stop words, edit `en/stopwords.txt` (one word per line) and
redeploy.

### Synonyms

Synonym expansion is handled in two different ways depending on the field:

- **Geography** synonyms use Lucene's `synonymGraph` filter, configured in
  `en/geo-synonyms.txt`. This is necessary because geography queries use
  field-scoped `userInput` (e.g.
  `{defaultIndex: "geographies"}userInput(@query)`), which labels query tokens
  with a field name. Vespa's semantic rules only match unlabeled tokens, so they
  can't be used here. TODO: investigate whether this is affecting multi-word
  geography queries.
- **Everything else** (title acronyms, `phaseout`, etc.) uses Vespa
  [semantic rules](https://docs.vespa.ai/en/linguistics/query-rewriting.html)
  defined in `vespa/app/rules/`. There are two rulebases:
  - `documents.sr` — the default, used for document search
  - `labels.sr` — used for label search (passed via `rules.rulebase=labels`),
    which extends `documents.sr` and adds `nz → net zero` (omitted from
    `documents.sr` to avoid conflating it with New Zealand in document search)

## References

- [Vespa Lucene Linguistics docs](https://docs.vespa.ai/en/linguistics/lucene-linguistics.html)
- [Lucene analysis overview](https://lucene.apache.org/core/9_11_1/core/org/apache/lucene/analysis/package-summary.html)

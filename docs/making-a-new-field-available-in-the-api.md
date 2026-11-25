# Making a new field available in the API

How to get a new document value from source data into Vespa and out through the
search API, and then into the frontend. Use it for any kind of field: one you
sort on, filter on, return in results, or group into facets.

```text
data-in-pipeline ──▶ Snowflake (dbt) ──▶ S3 export ──▶ vespa-feeder ──▶ Vespa ──▶ engine ──▶ API ──▶ frontend
   (attributes)     (derived fields)                  (pass-through)   (schema)
```

The worked example throughout is FUS-961, which added `attributes_created_at` so
the CCC homepage can show the most recently added cases.

## Before you start

Answer these first. They decide which steps you need.

| Question                                    | Why it matters                                                                                                                                                  |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Is the value already in the document?       | Most document metadata is already in `attributes`, and so in `attributes_string`, `attributes_double` or `attributes_boolean` in Vespa. If not, start at step 1 |
| What does the API need to do with it?       | Sort, range-filter, exact-filter, return, facet or rank. See [Do you need a new field?](#do-you-need-a-new-field)                                               |
| Where should the value be derived?          | In the Fusion dbt models. The feeder only passes it through. See step 3                                                                                         |
| Which document summaries need it?           | A field outside a summary is never returned. Vespa's `default` summary is not used. See step 2                                                                  |
| Does it change a field that already exists? | Changing a type or how a field is indexed needs a validation override, and every document needs re-feeding before the field is trustworthy                      |

### Do you need a new field?

Not always. The attribute maps already support some things without a schema
change.

| You want to                                                   | Use                                                                                                                            |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Exact-match filter on a string, number or boolean attribute   | Nothing new. `attributes.<key>` filters already work through `attributes_string`, `attributes_double` and `attributes_boolean` |
| Return a value that's in `attributes` on search results       | Nothing new. The engine builds `attributes` from `document_source`, so it's already in the API response                        |
| Sort on it                                                    | A new single-value `attribute` field. Vespa can't sort on a key inside a map                                                   |
| Range-filter on it (`gte`, `lt` and so on), e.g. dates        | A new single-value numeric `attribute` field, like `attributes_published_date`                                                 |
| Return it from a summary that doesn't carry `document_source` | A new field in that summary, e.g. `deprecated_slug` for the `sitemap` and `csv` summaries                                      |
| Group or facet on it                                          | A new `attribute` field, usually with `attribute: fast-search`                                                                 |
| Use it in ranking                                             | A new `attribute` field, plus a rank-profile change. Out of scope here; see `vespa/docs/` and the `vespa-debug` skill          |

If the first two rows cover it, stop here.

## PRs and release order

Merging to `main` in `search` deploys the API, the Vespa schema and the feeder
**at the same time** (`merge_to_main.yml`), and nothing makes one wait for
another. So the order has to come from separate PRs. Two rules decide it:

- **The schema must be live before anything uses the field.** Vespa rejects a
  feed update that writes a field it doesn't know, and rejects a query that
  sorts or filters on one, so the `/documents` request fails
- **Re-feed before the API offers the field.** Until the re-feed, the field is
  empty on every document. Sorts and filters on it still work, but return
  misleading results instead of failing, so nobody notices

| PR  | Repo                 | Contains                                                         | Merge when                                                                  |
| --- | -------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 0   | `navigator-backend`  | The value in data-in `attributes` (step 1), only if it's missing | Any time. Then wait for it to reach the Snowflake export                    |
| 1   | `search`             | Schema field, e2e test helper (steps 2 and 3)                    | After PR 0's value is in the export                                         |
| 1b  | `data-lake`          | The Fusion dbt column (step 3)                                   | After PR 1's schema is deployed, because the feed must not write it earlier |
| 2   | `search`             | Engine and API (step 5)                                          | After the re-feed (step 4) has finished and been checked                    |
| 3   | `navigator-frontend` | Using the field (step 6)                                         | After PR 2 is deployed                                                      |

When you can combine them:

- **No engine or API change needed** (e.g. the value is returned through
  `attributes`): PR 1 is the whole job, or you need no schema change at all. See
  [Do you need a new field?](#do-you-need-a-new-field)
- **The Fusion column can follow the schema straight away.** Fusion exports at
  01:00 UTC and the feeder runs at 08:30 UTC, so merging PR 1b once the Vespa
  deploy has finished is enough. Don't run the feeder by hand before then
- **PR 1 and PR 2 together** only if no client will call the new field until the
  re-feed is done. It saves a PR but loses the check that the data is right
  before anything relies on it. Prefer keeping them separate

## Steps

Each step names the repo it's in. Do them in this order. See
[PRs and release order](#prs-and-release-order) for which PR each one goes in.

### 1. Make sure the source has the value (`navigator-backend`)

The documents feed is built from the data-in `Document`. If the value isn't on
it, add it to `attributes` in `data-in-pipeline/app/transform/`.

- FUS-961 didn't need this: `_rds_timestamp_attributes` in `navigator_family.py`
  already passed `created` through
- Check the value really arrives in production, not just in the transform code.
  Query the dbt source table in Snowflake rather than trusting the code path
- Note its format. `created` arrives with and without a timezone, and with and
  without microseconds, and the parser has to handle all of these

### 2. Add it to the schema (`search`, `vespa/app/schemas/documents.sd`)

Add the field inside the `document documents` block.

```text
field attributes_created_at type long {
    indexing: attribute | summary
}
```

- **Type.** Store dates as `long` epoch seconds. Sorting or range-filtering
  strings compares text, which breaks when the formats are mixed
- **`attribute`.** Needed to sort, range-filter, group or facet. It's held in
  memory, so add it only if you need one of those
- **`fast-search`.** Add it only if you filter on the field with no other
  narrowing condition, or facet on it. It costs memory
- **`summary`.** Needed to return the field. Then add it to each
  `document-summary` block that should return it (`search`, `csv`, `sitemap` and
  so on). The engine picks a summary per request with `presentation.summary`,
  and never uses `default`
- **Naming.** Prefix fields taken from `attributes` with `attributes_`, e.g.
  `attributes_published_date`. The public API name is the dotted form,
  `attributes.published_date`

Adding a new field needs no validation override. Changing an existing field's
type or indexing does: the deploy output names the override to add to
`vespa/app/validation-overrides.xml`, with a short `until` date.

Test it by deploying to a local Vespa (`cd vespa && just up && just deploy`).
The e2e tests do this too. Nothing in the unit tests parses the schema, so a
mistake there only shows up at deploy.

### 3. Populate it: in the Fusion dbt models

A new field is empty until something writes it. The documents feeder is a
pass-through: every column of `fusion.published.vespa_documents` is assigned to
the Vespa field of the same name, so the value has to be computed in the Fusion
dbt project (`data-lake`, `fusion/models/transform/stg_vespa_documents.sql`).

- Add the column to `stg_vespa_documents` and select it in
  `fusion/models/published/vespa_documents.sql`, in the position the field has
  in `documents.sd`
- Document it with a `data_type` in both `schema.yml` files. The contract is
  enforced, so CI fails without it
- Extend the `test_vespa_documents_routes_principal_vs_member` unit test and its
  fixtures
- Derive it as Vespa expects it. A column derived from another one (like
  `distinct_concept_ids` or `attributes_created_at`) belongs in the final select
  of `stg_vespa_documents`, not in the feeder
- For a value that can be missing, decide between `''` (clears a stale value, as
  `deprecated_slug` does) and null (as `attributes_created_at` does, so the
  sort's `missing(...,last)` puts those documents last, rather than at 1970 or
  0). Parse timestamps with a timezone (`try_to_timestamp_tz`) rather than
  reading a timezone-less value as local time

The feeder needs no change: `document_update` in
`vespa-feeder/src/vespa_feeder/documents/flow.py` only wraps each row in an
update operation.

#### The e2e test helper

The e2e tests turn a test `Document` into a Vespa update with
`_source_document_to_vespa_update` in `tests/vespa_e2e.py`. It is separate from
the Fusion export, so the two can drift: it writes `document_source`, which the
API reads back, and builds the other fields itself.

So: if an e2e test needs the new field, populate it there too. If not, leave it
alone. Note that it has its own `_to_unix_timestamp`, which reads timezone-less
values as local time.

### 4. Deploy the schema and feeder, then re-feed

Merge PR 1 and wait for the Vespa deploy to finish. Merge the data-lake PR that
adds the column too, and let the Fusion run export it.

Then re-feed so every document gets the value. The documents feed runs daily
(the `search-vespa-feeder-documents` Prefect deployment, 08:30 UTC). To get it
sooner, run that deployment by hand once the Fusion export has the column.

Check it worked:

- Query Vespa for documents where the field is missing. Only documents without
  the source value should be left
- Spot-check a few documents' values against the source data

### 5. Expose it in the engine and API (`search`)

This is PR 2. Start it any time, but merge it only after step 4's re-feed has
been checked. Only the parts that match what the field is for.

| For           | Change                                                                                                                                                                                                                                                                                        |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sorting       | Add the public name to `sort_field_to_vespa_field_map` and a branch in `_document_sort_ranking_string` (`search/engines/vespa_query/sorting.py`). Add it to `DOCUMENTS_ORDER_BY_DESCRIPTION` (`api/utils.py`)                                                                                 |
| Range filters | Add the public name to `AttributesCondition.field` and handle it in `_build_condition_yql` (`search/engines/vespa_query/filters.py`), as `attributes.published_date` does. If callers send ISO dates, convert them at the boundary in `api/filters.py`                                        |
| Other filters | Map the public name to the Vespa field in `documents_filter_field_to_vespa_field_map` (`search/engines/dev_vespa/documents_search_engine.py`)                                                                                                                                                 |
| Returning it  | `/documents` returns the data-in `Document` shape (`search/data_in_models.py`), and a value in `attributes` already comes back through it. Don't add top-level keys to that shared shape. For other summaries, add it to the engine's model for that summary, e.g. `ExportDocument` for `csv` |

Tests:

- `tests/engines/dev_vespa/test_dev_vespa.py` for the sort string
- `tests/test_api_documents_sorting.py` for `order_by` accepting the field
- `tests/engines/vespa_query/test_filters.py` for filter YQL
- An e2e test in `tests/test_vespa_e2e.py` that feeds documents and checks the
  order or the matches. It needs the e2e test helper from step 3

Once it's deployed, call the API with the new sort or filter and check the
results by eye.

### 6. Use it in the frontend (`navigator-frontend`)

- Put new behaviour behind the `new-search` feature flag (`FeaturesContext`),
  and keep the old path working while the flag is off. A page that doesn't
  provide `FeaturesContext` always sees the default flags, so check the page
  does
- For a new sort, add a value to `SORT_VALUES` (`src/types/search/sort.ts`) and
  its `order_by` string to `SORT_PARAMS_LOOKUP` (`src/constants/sort.ts`). It
  only appears in a sort dropdown if you also add it to `SEARCH_SORT_OPTIONS`
- Merge the frontend only after the engine and API change is deployed

## Checklist

```text
[ ] Value is in data-in `attributes` and arrives in production       (navigator-backend)
[ ] Schema field: type, attribute / fast-search / summary chosen     (search: documents.sd)
[ ] Added to each document-summary that returns it                   (search: documents.sd)
[ ] Populated in the Fusion dbt models, with a unit test             (data-lake: fusion)
[ ] E2e test helper populates it, if an e2e test needs it            (search: tests/vespa_e2e.py)
[ ] Schema and feeder deployed, then re-fed and checked              (search: Prefect)
[ ] Engine and API: sort / filter / response model, with tests       (search, separate PR)
[ ] Frontend behind `new-search`, merged after the API is deployed   (navigator-frontend)
```

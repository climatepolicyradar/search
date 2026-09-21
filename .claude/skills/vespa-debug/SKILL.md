---
name: vespa-debug
description:
  Use when debugging Vespa search queries, ranking profiles, schema changes, or
  unexpected query results in the CPR search repo
---

# Vespa Debug Workflow

## Step 1 — Verify deploy state FIRST

Before touching any code, confirm the current schema is deployed:

```bash
cd vespa && just deploy
```

If deploy fails, fix that before debugging query results. Phantom issues from
stale deploys have caused many wasted sessions.

## Step 2 — Check Vespa is up

```bash
curl -s http://localhost:19071/ApplicationStatus | python3 -m json.tool | head -20
```

If not running: `cd vespa && just up && just deploy`

## Step 3 — Run a baseline query

Use `just get` to confirm actual behavior before forming a hypothesis:

```bash
cd vespa && just get "your search term"
```

Or a raw curl for more control:

```bash
curl -G "http://localhost:8080/search/" \
  --data-urlencode 'yql=select * from sources documents where userQuery()' \
  --data-urlencode 'query=your term' \
  --data-urlencode 'ranking=nativerank' \
  --data-urlencode 'hits=5'
```

## Step 4 — Explain the problem before proposing a fix

After seeing the actual output, state:

1. What the query returns
2. What it should return
3. Hypothesis for the gap

Only then propose a fix.

## Known Limitations (don't re-discover these)

- **Grouping + relevance**: Vespa cannot rank group keys by relevance score.
  Groups are ordered by document count or a fixed expression, not by the
  best-scoring document within the group. This is a fundamental platform
  limitation.
- **Rank profiles**: Check the available rank profiles in the schema that's used
  in search. Propose changes by creating a new rank profile that inherits from
  an existing rather than modifying an existing one, unless told otherwise.
- **Field indexing**: Match type (contains vs exact) must align with how the
  field is indexed. Check `index` vs `attribute` mode in the schema.
- **Synonym expansion**: Two mechanisms are in use. Geography aliases are
  resolved in Python (`GEOGRAPHY_ALIASES` in
  `search/engines/vespa_query/query_text.py`), which rewrites them to the
  canonical name as a quoted phrase in the `geo_query` parameter — Lucene
  synonyms can't express them on either side of the index, see
  `lucene-linguistics/README.md`. Everything else (title acronyms etc) uses
  Vespa semantic rules in `vespa/app/rules/` — `documents.sr` by default,
  `labels.sr` for label search (set via `rules.rulebase=labels`). If geography
  rewrites aren't firing, check `GEOGRAPHY_ALIASES` (no redeploy needed); for
  anything else check the relevant `.sr` file and redeploy.
- **Deploy target**: Local = `http://localhost:19071/`, use `just deploy` which
  already has the right target and wait time.

## Schemas

In `vespa/app/schemas/*.sd` one for documents, labels, and passages.

# FUS-67: Populate `pages` as a real multi-page array on Passage

Linear: [FUS-67](https://linear.app/climate-policy-radar/issue/FUS-67) Branch:
`feature/fus-67-populate-pages-as-a-real-multi-page-array-on-passage`

## Problem

1. `search/vespa/passages_feed_materializer.py`'s `_text_block_to_vespa_update`
   (feed for the live `GET /search/passages` route's Vespa schema,
   `passages.sd`) does not populate `page_number` into Vespa at all today — it's
   always `0` on every live passage result.
2. Where page data _is_ populated
   (`search/vespa/documents_feed_materializer.py`, feeding the `documents`
   schema's embedded passage struct), it only takes
   `block["pages"][0]["number"]` — the first page — discarding any subsequent
   pages when a text block spans multiple pages. The source
   `TextBlock.pages: list[PageRef]`
   (`search/vespa/sources/embeddings_input_v2.py`) already carries full
   multi-page data (each `PageRef` has `number` + `bounding_boxes`); it's just
   never propagated past the first entry.

## Acceptance criteria

- API response returns `pages`, to start with a list of integers representing
  the page numbers a passage is found on (bounding-box coords deferred to a
  future change).
- All references relating to that are updated accordingly — schema, feed
  materialiser(s), engines.
- Feed materialisers populate the field with real data, not hardcoded/default
  data.

## Out of scope

- Adding `type`/`type_confidence` to the API response, or closing the gap where
  those + page data aren't fed at all on routes that don't feed them today.
- Adding topics to the API response.
- Bounding box coordinates (deferred — AC says "to start with... list of
  integers").
- Actually deploying the new schema and re-running the feeder against prod Vespa
  — this spec covers code changes only. Deploy/re-feed is a manual operational
  follow-up.

## Decisions

Resolved during brainstorming (see conversation for full rationale):

- **Additive, not replacing:** `pages: list[int]` is added alongside the
  existing `page_number: int` everywhere it appears (Vespa schemas, feed
  materializers, engines, API model). `page_number` keeps its current first-page
  semantics and is not removed, to avoid a breaking API change.
- **`page_number` on `passages.sd` stays unpopulated:** the top-level
  `passages.sd` schema's `page_number` field remains as-is (still not fed) —
  strictly out of scope per this issue. Only the new `pages` field is populated
  there.
- **`documents.sd`'s embedded `passage` struct also gets `pages`:** the
  multi-page-discarding bug in `documents_passages_feed_materializer` is exactly
  problem statement #2, and FUS-45/FUS-30 (which this issue blocks) depend on
  document-page passage data being correct. Added additively alongside the
  existing `page_number`.
- **`fast-search` + `rank: filter` on `passages.sd`'s `pages` field:** confirmed
  via Slack thread with Kalyan/Chloe that page numbers will be used for
  **display and filtering, never ranking or sorting** (sorting uses block `idx`
  instead). Per Vespa docs, an `attribute` field without `fast-search` is a
  linear scan at query time — fine for display-only fields, but wrong for
  anything actually filtered on. Since filtering is a confirmed real use case
  (not speculative), `pages` on `passages.sd` gets:

  ```vespa
  field pages type array<int> {
      indexing: attribute | summary
      attribute: fast-search
      rank: filter
  }
  ```

  `rank: filter` tells Vespa this field never contributes to the ranking score,
  letting it skip rank-feature computation and use the filter-optimized
  posting-list layout.

- **`documents.sd`'s embedded `pages` stays display-only:** nothing in the AC or
  Slack thread calls for filtering on page number from within the
  document-drawer ("search inside a document") view. That struct's fields are
  already `indexing: summary`-only (no `attribute`), so no scan-performance risk
  today. Add `fast-search` there later, in isolation, if that changes.

## Changes

### 1. `vespa/app/schemas/passages.sd`

Add a new field:

```vespa
field pages type array<int> {
    indexing: attribute | summary
    attribute: fast-search
    rank: filter
}
```

Add `summary pages {}` to the `debug-summary` document-summary block.

Leave `page_number` untouched (still unpopulated on this schema).

### 2. `vespa/app/schemas/documents.sd`

Add to the embedded `passage` struct (additive, alongside existing
`page_number`):

```vespa
field pages type array<int> {}
```

with `field pages type array<int> { indexing: summary }` on the `passages`
field's struct-field block, matching the struct's existing display-only fields
(no `attribute`/`fast-search` — see decision above).

### 3. `search/vespa/passages_feed_materializer.py`

- `VespaPassageUpdate` TypedDict: add
  `pages: NotRequired[VespaAssign[list[int]]]`.
- `_text_block_to_vespa_update`: derive
  `pages = [p["number"] for p in block.get("pages", [])]` and assign onto
  `fields["pages"]` when non-empty — mirrors the existing optional-field pattern
  used for `heading_id`/`concepts`.

### 4. `search/vespa/documents_feed_materializer.py`

- `VespaDocumentPassage` TypedDict: add `pages: list[int]`.
- `documents_passages_feed_materializer`: alongside the existing
  `page_number: block["pages"][0]["number"] if block.get("pages") else 0`, add
  `pages: [p["number"] for p in block.get("pages", [])]`.

### 5. `search/engines/dev_vespa.py`

Both `Passage(...)` construction sites get a new `pages` argument:

- ~line 745 (embedded `documents.passages` struct, feeds the document-page /
  drawer "search inside" experience): `pages=passage.get("pages", [])`.
- ~line 1236 (top-level `passages` schema search, feeds `/search/passages`):
  `pages=fields.get("pages", [])`.

### 6. `search/passage.py`

Add to the `Passage` model, additive alongside `page_number`:

```python
pages: list[int] = Field(default_factory=list)
```

### 7. Tests

- `tests/vespa/test_passages_feed_materializer.py`: add a case asserting `pages`
  is populated from a multi-page `TextBlock.pages` list in
  `_text_block_to_vespa_update` (and that it's omitted/empty when
  `block["pages"]` is empty, consistent with existing optional-field tests).
- No test file currently exists for `documents_feed_materializer.py` (checked:
  `tests/vespa/` has none). Create
  `tests/vespa/test_documents_feed_materializer.py` with a case covering
  `documents_passages_feed_materializer` populating `pages` from a multi-page
  `TextBlock.pages` list (and `page_number` still resolving to the first page,
  unchanged).
- No existing test in `tests/engines/test_dev_vespa.py` covers `Passage(...)`
  construction at either site (checked: only label-parsing and sort-ranking
  tests exist there today). Add two new unit tests — one per construction site
  (embedded `documents.passages` struct, and top-level `passages` schema search)
  — asserting `pages` is read off the Vespa response fields onto the returned
  `Passage`.

## Verification

1. `_text_block_to_vespa_update` with a multi-page `TextBlock` → `pages`
   assigned as `[n1, n2, ...]` in the Vespa update fields.
2. `documents_passages_feed_materializer` with a multi-page `TextBlock` →
   `pages` in the embedded passage struct carries all page numbers, not just the
   first.
3. `dev_vespa.py`'s two `Passage(...)` sites populate `pages` from the
   corresponding Vespa fields.
4. `search/passage.py`'s `Passage` model has a `pages: list[int]` field,
   defaulting to `[]`.
5. Existing tests (chunking, heading_id, concepts) continue to pass unmodified —
   this change is additive only.

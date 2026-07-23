# FUS-67 follow-up: Page bounding boxes on Passage

Follow-up to [FUS-67](https://linear.app/climate-policy-radar/issue/FUS-67),
which added `pages: list[int]` to `Passage` but explicitly deferred bounding-box
coordinates. Branch: `feature/fus-67-page-bounding-boxes`.

## Problem

FUS-67 populated `pages` as a flat list of page numbers a passage appears on.
The source data (`TextBlock.pages: list[PageRef]` in
`search/vespa/sources/embeddings_input_v2.py`) already carries per-page
bounding-box geometry (`PageRef.bounding_boxes: list[BoundingBox]`, each a
polygon of `Coordinate{x, y}` points), but none of it reaches the API today.

## Acceptance criteria

- `GET /search/passages` returns per-page bounding-box geometry for each
  passage, in addition to the existing `pages: list[int]`.
- The geometry mirrors the source shape exactly (page number + a list of
  polygons, each a list of `{x, y}` points) — no lossy simplification to
  axis-aligned rects.
- Feed materializer populates the field with real data, not hardcoded.
- Existing `pages: list[int]` and its `fast-search`/`rank: filter` filtering
  behaviour (added in FUS-67) are unaffected.

## Out of scope

- `documents.sd`'s embedded `passage` struct — this change targets `passages.sd`
  / `GET /search/passages` only. Can be extended later if the document-drawer
  ("search inside a document") view needs geometry too.
- Actually deploying the new schema and re-running the feeder against prod Vespa
  — code changes only, same as FUS-67.

## Decisions

Resolved during brainstorming (see conversation for full rationale):

- **Vespa-side field is separate from the API-side shape.** The API's `Passage`
  model mirrors the source `PageRef`/`BoundingBox`/`Coordinate` nesting exactly
  (confirmed requirement). The Vespa schema does **not** need to mirror that
  same nesting — it's assembled into the API shape in the engine layer, same as
  other `Passage` fields already are.

- **Two separate Vespa fields, not one merged field.** Vespa's docs state that
  for nested structs (a struct-array whose elements themselves contain another
  struct-array), only `indexing: summary` is supported — no `attribute`,
  `fast-search`, or `rank: filter`. Our target geometry shape
  (`page → bounding_boxes → coordinates`) is exactly this kind of nesting. If
  bounding boxes were merged into the existing `pages` field, `pages` would lose
  the `fast-search` + `rank: filter` filtering FUS-67 deliberately added
  (confirmed via Slack thread as a real, non-speculative filtering use case).
  So:
  - `pages: array<int>` stays **completely unchanged** — same field, same
    `fast-search`/`rank: filter`, zero regression.
  - A new, separate field `page_bounding_boxes: array<page_boxes>` carries the
    geometry, `summary`-only throughout (nothing here needs filtering).

- **Self-contained struct per page, not parallel arrays.** `page_boxes` pairs
  `number` with that page's `bounding_boxes` in one struct, rather than relying
  on matching positions across separate parallel arrays (which would be fragile
  and hard to debug).

- **Scope narrowed to `passages.sd` only** (unlike FUS-67, which touched both
  `passages.sd` and `documents.sd`'s embedded struct). No confirmed need for
  geometry in the document-drawer view yet.

- **API model is additive, not a replacement.** `Passage.pages: list[int]` stays
  exactly as shipped in FUS-67. A new sibling field
  `pages_with_bounding_boxes: list[PageWithBoundingBoxes]` carries the richer
  per-page geometry, named to match the new Vespa field (`page_bounding_boxes`).

## Changes

### 1. `vespa/app/schemas/passages.sd`

Add new structs and a new field, alongside (not replacing) the existing
`pages: array<int>`:

```vespa
struct coordinate {
    field x type float {}
    field y type float {}
}
struct bounding_box {
    field coordinates type array<coordinate> {}
}
struct page_boxes {
    field number type int {}
    field bounding_boxes type array<bounding_box> {}
}
field page_bounding_boxes type array<page_boxes> {
    indexing: summary
}
```

Add `summary page_bounding_boxes {}` to the `debug-summary` document-summary
block, alongside the existing `summary pages {}`.

Leave the existing `pages: array<int>` field (with its `fast-search` +
`rank: filter`) completely untouched.

### 2. `search/vespa/passages_feed_materializer.py`

- `VespaPassageUpdate` TypedDict: add
  `page_bounding_boxes: NotRequired[VespaAssign[list[VespaPageBoxes]]]`, with a
  new `VespaPageBoxes` TypedDict (`number: int`,
  `bounding_boxes: list[VespaBoundingBox]`) and `VespaBoundingBox` TypedDict
  (`coordinates: list[VespaCoordinate]`), `VespaCoordinate` TypedDict
  (`x: float`, `y: float`) — mirroring `PageRef`/`BoundingBox`/`Coordinate` from
  `embeddings_input_v2.py`.
- `_text_block_to_vespa_update`: alongside the existing
  `pages = [page["number"] for page in block.get("pages", [])]`, add:

  ```python
  page_bounding_boxes = [
      {
          "number": page["number"],
          "bounding_boxes": [
              {
                  "coordinates": [
                      {"x": coord["x"], "y": coord["y"]}
                      for coord in box["coordinates"]
                  ]
              }
              for box in page["bounding_boxes"]
          ],
      }
      for page in block.get("pages", [])
  ]
  if page_bounding_boxes:
      fields["page_bounding_boxes"] = {"assign": page_bounding_boxes}
  ```

  Mirrors the existing optional-field pattern (`heading_id`, `concepts`,
  `pages`).

### 3. `search/engines/dev_vespa.py`

`DevVespaPassageSearchEngine.search()`'s `Passage(...)` construction site (~line
1236, the one already reading `pages=fields.get("pages", [])`) gets one more
argument:

```python
pages_with_bounding_boxes=fields.get("page_bounding_boxes", []),
```

The `documents.sd`-embedded construction site
(`DevVespaDocumentSearchEngine.search()`) is **not** touched — out of scope per
the schema-scope decision above.

### 4. `search/passage.py`

Add new Pydantic models mirroring the source/Vespa shapes, plus a new field on
`Passage`:

```python
class CoordinateModel(BaseModel):
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)


class BoundingBoxModel(BaseModel):
    coordinates: list[CoordinateModel] = Field(default_factory=list)


class PageWithBoundingBoxes(BaseModel):
    number: int = Field(default=0)
    bounding_boxes: list[BoundingBoxModel] = Field(default_factory=list)
```

And on `Passage`, additive alongside the existing `pages: list[int]`:

```python
pages_with_bounding_boxes: list[PageWithBoundingBoxes] = Field(
    default_factory=list
)
```

### 5. Tests

- `tests/vespa/test_passages_feed_materializer.py`: add a case asserting
  `page_bounding_boxes` is populated from a multi-page, multi-box `TextBlock` in
  `_text_block_to_vespa_update` (and omitted when `block["pages"]` is empty),
  consistent with the existing `pages` tests.
- `tests/engines/test_dev_vespa.py`: extend
  `test_passage_search_engine_reads_pages_from_top_level_passages_schema` (or
  add a new test alongside it) asserting `Passage.pages_with_bounding_boxes` is
  read correctly off `fields["page_bounding_boxes"]` in the Vespa response,
  following the same `patch.object(dev_vespa, "_execute_vespa_query", ...)`
  pattern used for `pages` in FUS-67.

## Verification

1. `_text_block_to_vespa_update` with a multi-page, multi-box `TextBlock` →
   `page_bounding_boxes` assigned as `[{number, bounding_boxes: [...]}, ...]` in
   the Vespa update fields, preserving every coordinate.
2. `_text_block_to_vespa_update` with no `pages` on the block → no
   `page_bounding_boxes` key in the update fields (matches existing `pages`
   omission behaviour).
3. `DevVespaPassageSearchEngine.search()` populates
   `Passage.pages_with_bounding_boxes` from `fields["page_bounding_boxes"]`.
4. `search/passage.py`'s `Passage` model has a
   `pages_with_bounding_boxes: list[PageWithBoundingBoxes]` field, defaulting to
   `[]`.
5. Existing `pages: list[int]` behaviour, its Vespa `fast-search`/
   `rank: filter` config, and all FUS-67 tests continue to pass unmodified —
   this change is additive only.

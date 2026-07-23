# FUS-67 follow-up: Page bounding boxes on Passage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-page bounding-box geometry to `GET /search/passages`,
alongside the existing `pages: list[int]` (added in FUS-67), without regressing
that field's Vespa `fast-search`/`rank: filter` filtering.

**Architecture:** A new, separate Vespa field `page_bounding_boxes` (nested
struct array, `summary`-only — Vespa disallows `attribute`/`fast-search` on
nested structs) carries `{number, bounding_boxes: [{coordinates: [{x, y}]}]}`
per page. The existing `pages: array<int>` field is completely untouched. The
materializer, engine, and API model each get one new field, additive alongside
their existing `pages` counterpart.

**Tech Stack:** Python 3.13, Vespa schema definitions (`.sd`), Pydantic, pytest,
`uv`.

**Spec:**
`docs/superpowers/specs/2026-07-22-fus-67-followup-page-bounding-boxes-design.md`

---

### Task 1: Vespa schema — add `page_bounding_boxes` to `passages.sd`

**Files:**

- Modify: `vespa/app/schemas/passages.sd:33-40` (insert after the existing
  `pages` field, before `heading_id`), and the `debug-summary` block
  (`vespa/app/schemas/passages.sd:107-127`)

- [ ] **Step 1: Add the new structs and field**

In `vespa/app/schemas/passages.sd`, insert immediately after the closing `}` of
the existing `pages` field (currently lines 33-37) and before
`field heading_id`:

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

The full block should read, in order: `pages` (unchanged) →
`coordinate`/`bounding_box`/`page_boxes` structs → `page_bounding_boxes` field →
`heading_id` (unchanged).

- [ ] **Step 2: Add to the debug-summary block**

In the same file, in the `document-summary debug-summary` block, add
`summary page_bounding_boxes {}` immediately after the existing
`summary pages {}` line.

- [ ] **Step 3: Verify the schema is syntactically valid**

Run: `find . -name "*.sd" -path "*passages*" | xargs cat | grep -c "^"`

This just confirms the file still parses as text (line count sanity check —
there's no local Vespa schema validator in this repo; actual schema validation
happens on deploy, which is out of scope per the spec). Read the full modified
file back and confirm brace balance visually: every `struct` and `field` block
you added has a matching closing `}`.

- [ ] **Step 4: Commit**

```bash
git add vespa/app/schemas/passages.sd
git commit -m "feat(vespa): add page_bounding_boxes field to passages schema"
```

---

### Task 2: Materializer — populate `page_bounding_boxes` in `passages_feed_materializer.py`

**Files:**

- Modify: `search/vespa/passages_feed_materializer.py`
- Test: `tests/vespa/test_passages_feed_materializer.py`

- [ ] **Step 1: Write the failing tests**

In `tests/vespa/test_passages_feed_materializer.py`, add these two tests
immediately after the existing
`test_text_block_to_vespa_update_omits_pages_when_block_has_none` (currently
ending at line 288):

```python
def test_text_block_to_vespa_update_includes_page_bounding_boxes() -> None:
    """page_bounding_boxes carries every page's boxes and coordinates."""
    block = _text_block(0)
    block["pages"] = [
        {
            "number": 3,
            "bounding_boxes": [
                {"coordinates": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]},
            ],
        },
        {
            "number": 4,
            "bounding_boxes": [
                {"coordinates": [{"x": 0.5, "y": 0.6}]},
                {"coordinates": [{"x": 0.7, "y": 0.8}]},
            ],
        },
    ]

    update = materializer._text_block_to_vespa_update(block, "doc-0")

    assert update["fields"].get("page_bounding_boxes") == {
        "assign": [
            {
                "number": 3,
                "bounding_boxes": [
                    {"coordinates": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]},
                ],
            },
            {
                "number": 4,
                "bounding_boxes": [
                    {"coordinates": [{"x": 0.5, "y": 0.6}]},
                    {"coordinates": [{"x": 0.7, "y": 0.8}]},
                ],
            },
        ]
    }


def test_text_block_to_vespa_update_omits_page_bounding_boxes_when_block_has_none() -> None:
    """page_bounding_boxes is absent from the update when the block has no pages."""
    update = materializer._text_block_to_vespa_update(_text_block(0), "doc-0")

    assert "page_bounding_boxes" not in update["fields"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
`uv run pytest tests/vespa/test_passages_feed_materializer.py::test_text_block_to_vespa_update_includes_page_bounding_boxes tests/vespa/test_passages_feed_materializer.py::test_text_block_to_vespa_update_omits_page_bounding_boxes_when_block_has_none -v`

Expected: both FAIL — `update["fields"].get("page_bounding_boxes")` is `None`
(field not yet produced by `_text_block_to_vespa_update`).

- [ ] **Step 3: Add the TypedDicts**

In `search/vespa/passages_feed_materializer.py`, add these new TypedDicts
immediately after the existing `VespaConceptField` (currently ending at line 49,
before `VespaPassageUpdate`):

```python
class VespaCoordinate(TypedDict):
    x: float
    y: float


class VespaBoundingBox(TypedDict):
    coordinates: list[VespaCoordinate]


class VespaPageBoxes(TypedDict):
    number: int
    bounding_boxes: list[VespaBoundingBox]
```

Then add one new field to `VespaPassageUpdate` (currently lines 52-63),
immediately after the existing `pages` line:

```python
    pages: NotRequired[VespaAssign[list[int]]]
    page_bounding_boxes: NotRequired[VespaAssign[list[VespaPageBoxes]]]
```

- [ ] **Step 4: Implement `_text_block_to_vespa_update`'s new block**

In the same file, in `_text_block_to_vespa_update`, immediately after the
existing:

```python
    pages = [page["number"] for page in block.get("pages", [])]
    if pages:
        fields["pages"] = {"assign": pages}
```

add:

```python
    page_bounding_boxes: list[VespaPageBoxes] = [
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/vespa/test_passages_feed_materializer.py -v`

Expected: all tests in the file PASS (the two new ones, plus every pre-existing
test in this file unaffected).

- [ ] **Step 6: Commit**

```bash
git add search/vespa/passages_feed_materializer.py tests/vespa/test_passages_feed_materializer.py
git commit -m "feat(vespa): populate page_bounding_boxes in passages feed materializer"
```

---

### Task 3: API model — add `pages_with_bounding_boxes` to `Passage`

**Files:**

- Modify: `search/passage.py`

- [ ] **Step 1: Add the new Pydantic models and field**

In `search/passage.py`, add these new models before the `Passage` class
definition:

```python
class CoordinateModel(BaseModel):
    """A single x/y point in a bounding-box polygon."""

    x: float = Field(default=0.0)
    y: float = Field(default=0.0)


class BoundingBoxModel(BaseModel):
    """A polygon (list of coordinate points) bounding part of a passage on a page."""

    coordinates: list[CoordinateModel] = Field(default_factory=list)


class PageWithBoundingBoxes(BaseModel):
    """A page number paired with the bounding boxes locating a passage on it."""

    number: int = Field(default=0)
    bounding_boxes: list[BoundingBoxModel] = Field(default_factory=list)
```

Then, on the `Passage` model, add one new field immediately after the existing
`pages: list[int] = Field(default_factory=list)` line:

```python
    pages_with_bounding_boxes: list[PageWithBoundingBoxes] = Field(
        default_factory=list
    )
```

- [ ] **Step 2: Verify the model constructs correctly**

Run:

```bash
uv run python -c "
from search.passage import Passage, PageWithBoundingBoxes, BoundingBoxModel, CoordinateModel

p = Passage(
    pages_with_bounding_boxes=[
        PageWithBoundingBoxes(
            number=3,
            bounding_boxes=[BoundingBoxModel(coordinates=[CoordinateModel(x=0.1, y=0.2)])],
        )
    ]
)
print(p.pages_with_bounding_boxes)
print(Passage().pages_with_bounding_boxes)
"
```

Expected output:

```
[PageWithBoundingBoxes(number=3, bounding_boxes=[BoundingBoxModel(coordinates=[CoordinateModel(x=0.1, y=0.2)])])]
[]
```

(First line shows the populated case; second confirms the default is an empty
list, matching the existing `pages` field's default behaviour.)

- [ ] **Step 3: Commit**

```bash
git add search/passage.py
git commit -m "feat(api): add pages_with_bounding_boxes field to Passage model"
```

---

### Task 4: Engine — read `page_bounding_boxes` onto `Passage` in `dev_vespa.py`

**Files:**

- Modify: `search/engines/dev_vespa.py` (the
  `DevVespaPassageSearchEngine.search()` `Passage(...)` construction site, ~line
  1236 — the one already setting `pages=fields.get("pages", [])`)
- Test: `tests/engines/test_dev_vespa.py`

- [ ] **Step 1: Write the failing test**

In `tests/engines/test_dev_vespa.py`, add this test immediately after the
existing
`test_passage_search_engine_reads_pages_from_top_level_passages_schema`:

```python
def test_passage_search_engine_reads_page_bounding_boxes_from_top_level_passages_schema() -> None:
    """The top-level passages schema's page_bounding_boxes field lands on Passage.pages_with_bounding_boxes."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    fake_response = {
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "block-0",
                        "idx": 0,
                        "text": "some text",
                        "language": "en",
                        "type": "Text",
                        "type_confidence": 1.0,
                        "page_number": 0,
                        "pages": [5, 6],
                        "page_bounding_boxes": [
                            {
                                "number": 5,
                                "bounding_boxes": [
                                    {"coordinates": [{"x": 0.1, "y": 0.2}]}
                                ],
                            },
                            {
                                "number": 6,
                                "bounding_boxes": [],
                            },
                        ],
                        "document_id": "doc-0",
                    }
                }
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    passage = result.results[0]
    assert len(passage.pages_with_bounding_boxes) == 2
    assert passage.pages_with_bounding_boxes[0].number == 5
    assert passage.pages_with_bounding_boxes[0].bounding_boxes[0].coordinates[0].x == 0.1
    assert passage.pages_with_bounding_boxes[1].number == 6
    assert passage.pages_with_bounding_boxes[1].bounding_boxes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
`uv run pytest tests/engines/test_dev_vespa.py::test_passage_search_engine_reads_page_bounding_boxes_from_top_level_passages_schema -v`

Expected: FAIL — `Passage.pages_with_bounding_boxes` is `[]` (the construction
site doesn't set it yet), so `len(passage.pages_with_bounding_boxes) == 2`
fails.

- [ ] **Step 3: Implement**

In `search/engines/dev_vespa.py`, in `DevVespaPassageSearchEngine.search()`,
find the `Passage(...)` construction site that already has
`pages=fields.get("pages", []),` and add immediately after it:

```python
                    pages_with_bounding_boxes=fields.get("page_bounding_boxes", []),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/engines/test_dev_vespa.py -v`

Expected: all tests in the file PASS, including the new one and every
pre-existing test (in particular
`test_document_search_engine_reads_pages_from_embedded_passage_struct`, which
must remain unaffected since Task 4 only touches the
`DevVespaPassageSearchEngine` construction site, not
`DevVespaDocumentSearchEngine`'s).

- [ ] **Step 5: Commit**

```bash
git add search/engines/dev_vespa.py tests/engines/test_dev_vespa.py
git commit -m "feat(engines): read page_bounding_boxes onto Passage in DevVespaPassageSearchEngine"
```

---

### Task 5: Full verification pass

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full non-e2e test suite**

Run:
`uv run pytest tests/ -q -k "not e2e" --ignore=tests/api/test_router.py --ignore=tests/test_api_labels.py`

Expected: all tests pass (the two `--ignore`d files have a pre-existing,
unrelated `.env`/`EnvSettings` environmental failure — confirmed earlier in this
project, not caused by this change).

- [ ] **Step 2: Lint and format check**

Run:

```bash
uv run ruff check search/vespa/passages_feed_materializer.py search/passage.py search/engines/dev_vespa.py tests/vespa/test_passages_feed_materializer.py tests/engines/test_dev_vespa.py
uv run ruff format --diff search/vespa/passages_feed_materializer.py search/passage.py search/engines/dev_vespa.py tests/vespa/test_passages_feed_materializer.py tests/engines/test_dev_vespa.py
```

Expected: `ruff check` reports no issues; `ruff format --diff` reports no
changes needed (or apply `ruff format` directly if it does, then re-run
`check`).

- [ ] **Step 3: Confirm additive-only diff**

Run: `git diff main --stat` (or `git diff <base-branch>..HEAD --stat` if not on
`main`)

Expected: only the 5 files touched across Tasks 1-4 show changes (plus the two
spec/plan doc files); no unrelated files modified; no deletions of existing
fields/tests.

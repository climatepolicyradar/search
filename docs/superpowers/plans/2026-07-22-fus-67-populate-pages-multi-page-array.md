# FUS-67: Populate `pages` as a real multi-page array on Passage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `pages: list[int]` field to the Passage model, additive
alongside the existing `page_number: int`, populated correctly from
`TextBlock.pages` (all pages, not just the first) across the passages feed
materializer, the documents feed materializer, both Vespa schemas, both search
engines, and the API model.

**Architecture:** Additive change threaded through the existing pipeline:
`embeddings_input_v2.TextBlock.pages` (source, unchanged) → feed materializers
(derive `pages: list[int]`) → Vespa schemas (`array<int>` field) → search
engines (read field into `Passage.pages`) → API model (`Passage.pages`).
`passages.sd`'s `pages` field gets `attribute: fast-search` + `rank: filter`
because page filtering is a confirmed real use case (display + filter, never
ranking/sorting — confirmed via Slack with Kalyan/Chloe); `documents.sd`'s
embedded struct field stays display-only (`indexing: summary`, no `attribute`).

**Tech Stack:** Python, Pydantic, TypedDict, Vespa schema definitions (`.sd`),
pytest.

**Spec:**
`docs/superpowers/specs/2026-07-22-fus-67-populate-pages-multi-page-array-design.md`

---

## File Structure

- Modify: `vespa/app/schemas/passages.sd` — add `pages` field (attribute,
  fast-search, filter) + debug-summary entry.
- Modify: `vespa/app/schemas/documents.sd` — add `pages` field to embedded
  `passage` struct (display-only).
- Modify: `search/vespa/passages_feed_materializer.py` — derive and assign
  `pages` in `_text_block_to_vespa_update`.
- Modify: `search/vespa/documents_feed_materializer.py` — derive and assign
  `pages` in `documents_passages_feed_materializer`.
- Modify: `search/engines/dev_vespa.py` — read `pages` onto `Passage(...)` at
  both construction sites.
- Modify: `search/passage.py` — add `pages: list[int]` to the `Passage` model.
- Modify: `tests/vespa/test_passages_feed_materializer.py` — new test case for
  `pages` in `_text_block_to_vespa_update`.
- Create: `tests/vespa/test_documents_feed_materializer.py` — new test file, one
  test for `pages` in `documents_passages_feed_materializer`.
- Modify: `tests/engines/test_dev_vespa.py` — two new tests, one per
  `Passage(...)` construction site.

Tasks are ordered bottom-up (schema → materializers → engines → API model →
tests threaded through each), each independently committable.

---

### Task 1: Add `pages` field to `passages.sd` schema

**Files:**

- Modify: `vespa/app/schemas/passages.sd`

- [ ] **Step 1: Add the `pages` field to the `passages` document block**

In `vespa/app/schemas/passages.sd`, add this field immediately after the
existing `page_number` field (after line 32, before `field heading_id`):

```vespa
        field pages type array<int> {
            indexing: attribute | summary
            attribute: fast-search
            rank: filter
        }
```

- [ ] **Step 2: Add `pages` to the `debug-summary` document-summary**

In the same file, in the `document-summary debug-summary` block, add
`summary pages {}` immediately after the existing `summary page_number {}` line:

```vespa
        summary page_number {}
        summary pages {}
```

- [ ] **Step 3: Verify the schema file is syntactically consistent**

Run: `grep -A4 "field pages" vespa/app/schemas/passages.sd` Expected: shows the
new field block with `indexing: attribute | summary`, `attribute: fast-search`,
`rank: filter`.

- [ ] **Step 4: Commit**

```bash
git add vespa/app/schemas/passages.sd
git commit -m "feat(vespa): add pages array field to passages schema"
```

---

### Task 2: Add `pages` field to `documents.sd` embedded passage struct

**Files:**

- Modify: `vespa/app/schemas/documents.sd`

- [ ] **Step 1: Add `pages` to the `passage` struct definition**

In `vespa/app/schemas/documents.sd`, the `struct passage` block (lines 121-129)
currently reads:

```vespa
        struct passage {
            field text_block_id type string {}
            field language type string {}
            field type type string {}
            field type_confidence type float {}
            field page_number type int {}
            field text type string {}
            field heading_id type string {}
        }
```

Add `field pages type array<int> {}` immediately after
`field page_number type int {}`:

```vespa
        struct passage {
            field text_block_id type string {}
            field language type string {}
            field type type string {}
            field type_confidence type float {}
            field page_number type int {}
            field pages type array<int> {}
            field text type string {}
            field heading_id type string {}
        }
```

- [ ] **Step 2: Verify the `passages` field's indexing is unaffected**

The `field passages type array<passage> { indexing: summary }` block (lines
130-132) does not need per-struct-field overrides today (no `struct-field`
blocks exist for `passage` in this schema, unlike the `label`/`concept` structs)
— no change needed there. Confirm by checking:

Run: `sed -n '120,133p' vespa/app/schemas/documents.sd` Expected: shows the
updated `passage` struct with `pages`, followed by the unchanged
`field passages type array<passage> { indexing: summary }` block with no
`struct-field` entries.

- [ ] **Step 3: Commit**

```bash
git add vespa/app/schemas/documents.sd
git commit -m "feat(vespa): add pages array field to documents passage struct"
```

---

### Task 3: Populate `pages` in `passages_feed_materializer.py`

**Files:**

- Modify: `search/vespa/passages_feed_materializer.py`
- Test: `tests/vespa/test_passages_feed_materializer.py`

- [ ] **Step 1: Write the failing test**

In `tests/vespa/test_passages_feed_materializer.py`, add this test after
`test_text_block_to_vespa_update_includes_and_omits_concepts` (after line 268):

```python
def test_text_block_to_vespa_update_includes_pages_from_multi_page_block() -> None:
    """pages is assigned as the full list of page numbers, not just the first."""
    block = _text_block(0)
    block["pages"] = [
        {"number": 3, "bounding_boxes": []},
        {"number": 4, "bounding_boxes": []},
    ]

    update = materializer._text_block_to_vespa_update(block, "doc-0")

    assert update["fields"].get("pages") == {"assign": [3, 4]}


def test_text_block_to_vespa_update_omits_pages_when_block_has_none() -> None:
    """pages is absent from the update when the source block has no pages."""
    update = materializer._text_block_to_vespa_update(_text_block(0), "doc-0")

    assert "pages" not in update["fields"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
`uv run pytest tests/vespa/test_passages_feed_materializer.py -k "pages" -v`
Expected: FAIL — `AssertionError` because `update["fields"]` has no `"pages"`
key yet (both new tests fail).

- [ ] **Step 3: Add `pages` to `VespaPassageUpdate` TypedDict**

In `search/vespa/passages_feed_materializer.py`, the `VespaPassageUpdate`
TypedDict (lines 52-62) currently ends with
`concepts: NotRequired[VespaAssign[list[VespaConceptField]]]`. Add a new field
after it:

```python
class VespaPassageUpdate(TypedDict):
    id: VespaAssign[str]
    idx: VespaAssign[int]
    language: VespaAssign[str]
    text: VespaAssign[str]
    document_id: VespaAssign[str]
    document_ref: VespaAssign[str]
    principal_document_ref: NotRequired[VespaAssign[str]]
    heading_id: NotRequired[VespaAssign[str]]
    heading_text: NotRequired[VespaAssign[str]]
    concepts: NotRequired[VespaAssign[list[VespaConceptField]]]
    pages: NotRequired[VespaAssign[list[int]]]
```

- [ ] **Step 4: Derive and assign `pages` in `_text_block_to_vespa_update`**

In the same file, in `_text_block_to_vespa_update` (lines 126-170), add this
block right after the `if concepts:` block (after line 164, before the `return`
statement):

```python
    pages = [page["number"] for page in block.get("pages", [])]
    if pages:
        fields["pages"] = {"assign": pages}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/vespa/test_passages_feed_materializer.py -v` Expected:
PASS — all tests in the file pass, including the two new ones and all
pre-existing ones (chunking, heading_id, concepts).

- [ ] **Step 6: Commit**

```bash
git add search/vespa/passages_feed_materializer.py tests/vespa/test_passages_feed_materializer.py
git commit -m "feat(vespa): populate pages array in passages feed materializer"
```

---

### Task 4: Populate `pages` in `documents_feed_materializer.py`

**Files:**

- Modify: `search/vespa/documents_feed_materializer.py`
- Create: `tests/vespa/test_documents_feed_materializer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/vespa/test_documents_feed_materializer.py`:

```python
"""Unit tests for documents_feed_materializer's passage-derived fields."""

from unittest.mock import MagicMock, patch

import orjson

from search.vespa import documents_feed_materializer as materializer
from search.vespa.sources.embeddings_input_v2 import TextBlock


def _text_block(idx: int, pages: list[dict] | None = None) -> TextBlock:
    return {
        "language": "en",
        "type": "Text",
        "type_confidence": 1.0,
        "text": f"passage {idx}",
        "id": f"block-{idx}",
        "idx": idx,
        "pages": pages if pages is not None else [],
    }


def test_documents_passages_feed_materializer_populates_pages_and_page_number() -> None:
    """pages carries every page number; page_number keeps its first-page value."""
    block = _text_block(
        0,
        pages=[
            {"number": 3, "bounding_boxes": []},
            {"number": 4, "bounding_boxes": []},
        ],
    )

    with (
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=iter(
                [("doc-0", {"pdf_data": {"text_blocks": [block]}})]
            ),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        plain_file = next(
            call.args[0]
            for call in upload_calls
            if call.args[2].endswith(".jsonl") and not call.args[2].endswith(".jsonl.gz")
        )

        with open(plain_file, "rb") as f:
            update = orjson.loads(f.readline())

        passages = update["fields"]["passages"]["assign"]
        assert passages[0]["page_number"] == 3
        assert passages[0]["pages"] == [3, 4]


def test_documents_passages_feed_materializer_defaults_when_no_pages() -> None:
    """page_number defaults to 0 and pages to an empty list when the block has no pages."""
    block = _text_block(0, pages=[])

    with (
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=iter(
                [("doc-0", {"pdf_data": {"text_blocks": [block]}})]
            ),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        plain_file = next(
            call.args[0]
            for call in upload_calls
            if call.args[2].endswith(".jsonl") and not call.args[2].endswith(".jsonl.gz")
        )

        with open(plain_file, "rb") as f:
            update = orjson.loads(f.readline())

        passages = update["fields"]["passages"]["assign"]
        assert passages[0]["page_number"] == 0
        assert passages[0]["pages"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/vespa/test_documents_feed_materializer.py -v`
Expected: FAIL — `KeyError: 'pages'` when asserting `passages[0]["pages"]`,
since the materializer doesn't emit that key yet.

- [ ] **Step 3: Add `pages` to `VespaDocumentPassage` TypedDict**

In `search/vespa/documents_feed_materializer.py`, the `VespaDocumentPassage`
TypedDict (lines 226-233) currently reads:

```python
class VespaDocumentPassage(TypedDict):
    text_block_id: str
    language: str
    type: str
    type_confidence: float
    page_number: int
    text: str
    heading_id: NotRequired[str | None]
```

Add `pages: list[int]` after `page_number`:

```python
class VespaDocumentPassage(TypedDict):
    text_block_id: str
    language: str
    type: str
    type_confidence: float
    page_number: int
    pages: list[int]
    text: str
    heading_id: NotRequired[str | None]
```

- [ ] **Step 4: Derive and assign `pages` in
      `documents_passages_feed_materializer`**

In the same file, in `documents_passages_feed_materializer` (lines 359-407), the
passage dict comprehension (lines 371-384) currently reads:

```python
            passages: list[VespaDocumentPassage] = [
                {
                    "text_block_id": block["id"],
                    "language": block["language"],
                    "type": block["type"],
                    "type_confidence": block["type_confidence"],
                    "page_number": block["pages"][0]["number"]
                    if block.get("pages")
                    else 0,
                    "text": block["text"],
                    "heading_id": block.get("heading_id"),
                }
                for block in text_blocks
            ]
```

Add a `"pages"` key after `"page_number"`:

```python
            passages: list[VespaDocumentPassage] = [
                {
                    "text_block_id": block["id"],
                    "language": block["language"],
                    "type": block["type"],
                    "type_confidence": block["type_confidence"],
                    "page_number": block["pages"][0]["number"]
                    if block.get("pages")
                    else 0,
                    "pages": [page["number"] for page in block.get("pages", [])],
                    "text": block["text"],
                    "heading_id": block.get("heading_id"),
                }
                for block in text_blocks
            ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/vespa/test_documents_feed_materializer.py -v`
Expected: PASS — both new tests pass.

- [ ] **Step 6: Run the full vespa test directory to check for regressions**

Run: `uv run pytest tests/vespa/ -v` Expected: PASS — all tests pass, including
the pre-existing `documents_feed_materializer`-adjacent tests (concepts,
principal concepts) if any exist, and everything from Task 3.

- [ ] **Step 7: Commit**

```bash
git add search/vespa/documents_feed_materializer.py tests/vespa/test_documents_feed_materializer.py
git commit -m "feat(vespa): populate pages array in documents feed materializer"
```

---

### Task 5: Add `pages` to the API `Passage` model

**Files:**

- Modify: `search/passage.py`

- [ ] **Step 1: Add the `pages` field**

In `search/passage.py`, the `Passage` model currently reads (lines 4-23):

```python
class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    idx: int = Field(default=0)
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    page_number: int = Field(default=0)
    heading_id: str | None = Field(default=None)
    heading_text: str | None = Field(default=None)
    document_id: str = Field(default="")
    principal_id: str | None = Field(default=None)
    # TODO: this is Vespa's own on-the-fly tokenization of `text` (via
    # debug-summary), NOT the same as the Snowflake model's `tokens` column
    # (Python-side tokenization fed INTO Vespa). Will likely remove this field
    # in the future - just here for now to expose for discovery for the UI
    # project.
    tokens: list[str] = Field(default_factory=list)
```

Add `pages: list[int] = Field(default_factory=list)` immediately after
`page_number`:

```python
class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    idx: int = Field(default=0)
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    page_number: int = Field(default=0)
    pages: list[int] = Field(default_factory=list)
    heading_id: str | None = Field(default=None)
    heading_text: str | None = Field(default=None)
    document_id: str = Field(default="")
    principal_id: str | None = Field(default=None)
    # TODO: this is Vespa's own on-the-fly tokenization of `text` (via
    # debug-summary), NOT the same as the Snowflake model's `tokens` column
    # (Python-side tokenization fed INTO Vespa). Will likely remove this field
    # in the future - just here for now to expose for discovery for the UI
    # project.
    tokens: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Verify the model still constructs with no arguments**

Run:
`uv run python -c "from search.passage import Passage; p = Passage(); print(p.pages, p.page_number)"`
Expected output: `[] 0`

- [ ] **Step 3: Commit**

```bash
git add search/passage.py
git commit -m "feat(api): add pages field to Passage model"
```

---

### Task 6: Read `pages` onto `Passage` in both `dev_vespa.py` engines

**Files:**

- Modify: `search/engines/dev_vespa.py`
- Test: `tests/engines/test_dev_vespa.py`

Both engine classes call the module-level `_execute_vespa_query` function to hit
Vespa over HTTP. Patching `dev_vespa._execute_vespa_query` (the same pattern
used for `boto3.client` in the materializer tests) lets these tests call the
real `.search()` methods end-to-end with a fake Vespa response, actually
exercising the production code in this task rather than re-testing the `Passage`
model in isolation.

- [ ] **Step 1: Write the failing tests**

In `tests/engines/test_dev_vespa.py`, add these imports at the top, after the
existing `from search.engines.dev_vespa import (...)` block:

```python
from unittest.mock import patch

from search.engines import Pagination, dev_vespa
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
```

Then add these two tests at the end of the file:

```python
def test_document_search_engine_reads_pages_from_embedded_passage_struct() -> None:
    """The embedded documents.passages struct's pages field lands on Passage.pages."""
    settings = Settings(
        vespa_endpoint="http://localhost:8080", vespa_read_token="token"
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

    fake_response = {
        "root": {
            "children": [
                {
                    "id": "id:documents:documents::doc-0",
                    "fields": {
                        "document_source": (
                            '{"id": "doc-0", "labels": [], "documents": []}'
                        ),
                        "passages": [
                            {
                                "text_block_id": "block-0",
                                "idx": 0,
                                "language": "en",
                                "type": "Text",
                                "type_confidence": 1.0,
                                "page_number": 3,
                                "pages": [3, 4],
                                "heading_id": None,
                            }
                        ],
                        "passages_text": ["<hi>needle</hi> in a haystack"],
                    },
                }
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].passages[0].pages == [3, 4]


def test_passage_search_engine_reads_pages_from_top_level_passages_schema() -> None:
    """The top-level passages schema's pages field lands on Passage.pages."""
    settings = Settings(
        vespa_endpoint="http://localhost:8080", vespa_read_token="token"
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

    assert result.results[0].pages == [5, 6]
```

Note: `test_document_search_engine_reads_pages_from_embedded_passage_struct`
asserts `result.results[0].passages[0].pages` —
`DevVespaDocumentSearchEngine.search()` returns `Document` objects with a
`passages: list[Passage]` field, so the `Passage` under test is nested one level
down, unlike the passage-engine test where the top-level result _is_ the
`Passage`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engines/test_dev_vespa.py -k "pages" -v` Expected:
FAIL —
`TypeError: Passage.__init__() got an unexpected keyword argument 'pages'` for
`test_passage_search_engine_reads_pages_from_top_level_passages_schema`, and
either the same error or `AssertionError` (empty `pages`) for
`test_document_search_engine_reads_pages_from_embedded_passage_struct`, since
neither `Passage(...)` construction site in `dev_vespa.py` reads `pages` yet.

- [ ] **Step 3: Add `pages` to both `Passage(...)` construction sites in
      `dev_vespa.py`**

In `search/engines/dev_vespa.py`, the first site (~line 744-756, inside
`DevVespaDocumentSearchEngine`) currently reads:

```python
                passages.append(
                    Passage(
                        text_block_id=passage.get("text_block_id", ""),
                        idx=passage.get("idx", 0),
                        text=bolded_text,
                        language=passage.get("language", ""),
                        type=passage.get("type", ""),
                        type_confidence=passage.get("type_confidence", 0.0),
                        page_number=passage.get("page_number", 0),
                        heading_id=passage.get("heading_id"),
                        document_id=document_id,
                    )
                )
```

Add `pages=passage.get("pages", []),` after `page_number`:

```python
                passages.append(
                    Passage(
                        text_block_id=passage.get("text_block_id", ""),
                        idx=passage.get("idx", 0),
                        text=bolded_text,
                        language=passage.get("language", ""),
                        type=passage.get("type", ""),
                        type_confidence=passage.get("type_confidence", 0.0),
                        page_number=passage.get("page_number", 0),
                        pages=passage.get("pages", []),
                        heading_id=passage.get("heading_id"),
                        document_id=document_id,
                    )
                )
```

The second site (~line 1236-1250, inside `DevVespaPassageSearchEngine`)
currently reads:

```python
            passages.append(
                Passage(
                    text_block_id=fields.get("id", ""),
                    idx=fields.get("idx", 0),
                    text=fields.get("text", ""),
                    language=fields.get("language", ""),
                    type=fields.get("type", ""),
                    type_confidence=fields.get("type_confidence", 0.0),
                    page_number=fields.get("page_number", 0),
                    heading_id=fields.get("heading_id"),
                    heading_text=fields.get("heading_text"),
                    document_id=fields.get("document_id", ""),
                    principal_id=fields.get("principal_id"),
                    tokens=fields.get("text_tokens") or [],
                )
            )
```

Add `pages=fields.get("pages", []),` after `page_number`:

```python
            passages.append(
                Passage(
                    text_block_id=fields.get("id", ""),
                    idx=fields.get("idx", 0),
                    text=fields.get("text", ""),
                    language=fields.get("language", ""),
                    type=fields.get("type", ""),
                    type_confidence=fields.get("type_confidence", 0.0),
                    page_number=fields.get("page_number", 0),
                    pages=fields.get("pages", []),
                    heading_id=fields.get("heading_id"),
                    heading_text=fields.get("heading_text"),
                    document_id=fields.get("document_id", ""),
                    principal_id=fields.get("principal_id"),
                    tokens=fields.get("text_tokens") or [],
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engines/test_dev_vespa.py -v` Expected: PASS — all
tests in the file pass, including the two new `pages`-related tests and the
pre-existing `test_parse_label_type_id_value` /
`test_document_sort_ranking_string_puts_missing_values_last` tests.

- [ ] **Step 5: Commit**

```bash
git add search/engines/dev_vespa.py tests/engines/test_dev_vespa.py
git commit -m "feat(engines): read pages field onto Passage in dev_vespa engines"
```

---

### Task 7: Full regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v` Expected: PASS — every test passes, no
regressions. This exercises Tasks 1-6 together plus all pre-existing tests
untouched by this plan (chunking, concepts, sort ranking, filters, etc.).

- [ ] **Step 2: Confirm no unrelated files changed**

Run: `git status` Expected: working tree clean (everything from Tasks 1-6
already committed), on branch
`feature/fus-67-populate-pages-as-a-real-multi-page-array-on-passage`.

- [ ] **Step 3: Review the full diff against origin/main for sanity**

Run: `git diff origin/main..HEAD --stat` Expected: shows the 9 files listed in
"File Structure" above (2 schemas, 2 materializers, 1 engine, 1 API model, 3
test files), plus `search/vespa/passages_feed_materializer.py`'s pre-existing
"Update logging" diff already on this branch from before this plan started
(unrelated print-statement additions, not touched by this plan). That prior
commit is expected pre-existing branch history — do not remove or amend it
unless asked.

---

## Notes for the engineer

- **Bounding boxes are out of scope.** `pages` is a flat `list[int]` of page
  numbers only, per the spec's explicit deferral.
- **`page_number` is untouched everywhere.** It keeps its current (partially
  broken, out-of-scope-to-fix-further) behavior on `passages.sd` (never
  populated) and its first-page behavior on `documents.sd` (populated,
  unchanged).
- **`fast-search` + `rank: filter` only apply to `passages.sd`'s `pages`
  field**, not the `documents.sd` embedded struct's `pages` — confirmed via
  Slack thread that page filtering is a real use case for the top-level passages
  route, not (yet) for the document-drawer view.
- **No deploy/re-feed in this plan.** Actually deploying the new schema fields
  to Vespa and re-running the materializers/feeder against real data is a manual
  operational step, out of scope here.

# FUS-48: `/search/passages` — expose `idx` on the Passage model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GET /search/passages` (and the passages embedded in document
search results) expose all fields available in the target Passage model
referenced in Linear ticket FUS-48 (Snowflake
`pipeline_embeddings_input_with_topics_v2`), without renaming any existing
fields.

**Scope decision (confirmed with Patrick Fawbert Mills in Slack, 2026-07-20,
thread in #C09R5D5KCRK):** field names do **not** need to match the target model
1:1 for this first pass — "main thing in the first pass is to get access to all
of the data we can see in this model." The current `Passage` model
(`text_block_id`, `text`, `language`, `type`, `type_confidence`, `page_number`,
`heading_id`, `document_id`, computed `id`) already covers every target-model
field except `idx` (index of the text block within the document) under different
names:

| Target model field                    | Current `Passage` field              | Status                                                                |
| ------------------------------------- | ------------------------------------ | --------------------------------------------------------------------- |
| `document_id`                         | `document_id`                        | ✅ already present                                                    |
| `id`                                  | `id` (computed from `text_block_id`) | ✅ already present                                                    |
| `idx`                                 | —                                    | ❌ missing — this is the only real gap                                |
| `language`                            | `language`                           | ✅ already present                                                    |
| `content_type`                        | `type`                               | ✅ already present (different name, that's fine)                      |
| `type_confidence`                     | `type_confidence`                    | ✅ already present                                                    |
| `pages`                               | `page_number`                        | ✅ already present (different name/shape, that's fine for first pass) |
| `content`                             | `text`                               | ✅ already present (different name, that's fine)                      |
| `heading_id`                          | `heading_id`                         | ✅ already present                                                    |
| `tokens`, `serialised_text`, `topics` | —                                    | out of scope (no data source / explicitly excluded per ticket)        |

**Architecture:** `Passage` (`search/passage.py`) is a Pydantic model returned
by two Vespa-backed search engines: `DevVespaPassageSearchEngine`
(`search/engines/dev_vespa.py`, wired to the live `GET /search/passages` route)
and `DevVespaDocumentSearchEngine` (same file, builds `Document.passages`,
embedded passage matches on document search). Both construct `Passage` objects
from raw Vespa hit fields. The Vespa `passages` schema
(`vespa/app/schemas/passages.sd`) already has an `idx: int` field, and
`DevVespaPassageSearchEngine`'s query already fetches it via `select *` — it's
just not read into the `Passage` constructor call. Adding `idx` requires: (1) a
new field on the `Passage` model, (2) reading `fields.get("idx", 0)` at both
call sites.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, Hypothesis.

---

### Task 1: Add `idx` field to the `Passage` model

**Files:**

- Modify: `search/passage.py`

- [ ] **Step 1: Add the field**

Current content of `search/passage.py`:

```python
from pydantic import BaseModel, Field, computed_field


class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    page_number: int = Field(default=0)
    heading_id: str | None = Field(default=None)
    document_id: str = Field(default="")

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id
```

Add a new `idx: int` field (index of this text block within the parent document,
matching the target model's `idx` column). Insert it directly after
`text_block_id` for readability:

```python
from pydantic import BaseModel, Field, computed_field


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
    document_id: str = Field(default="")

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id
```

- [ ] **Step 2: Confirm it imports cleanly**

Run:
`cd /Users/katy/Code/search && uv run python -c "from search.passage import Passage; print(Passage())"`
Expected: prints a `Passage` instance including `idx=0`, no errors.

- [ ] **Step 3: Commit**

```bash
git add search/passage.py
git commit -m "feat: add idx field to Passage model (FUS-48)"
```

---

### Task 2: Populate `idx` in `DevVespaPassageSearchEngine` (the live route's engine)

**Files:**

- Modify: `search/engines/dev_vespa.py` (inside
  `DevVespaPassageSearchEngine.search`, find by content match — approx. lines
  1191-1204)

- [ ] **Step 1: Add `idx` to the hit-to-Passage mapping**

Find this block:

```python
        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            passages.append(
                Passage(
                    text_block_id=fields.get("id", ""),
                    text=fields.get("text", ""),
                    language=fields.get("language", ""),
                    type=fields.get("type", ""),
                    type_confidence=fields.get("type_confidence", 0.0),
                    page_number=fields.get("page_number", 0),
                    heading_id=fields.get("heading_id"),
                    document_id=fields.get("document_id", ""),
                )
            )
```

Replace with (only the added `idx=` line changes):

```python
        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
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
                    document_id=fields.get("document_id", ""),
                )
            )
```

- [ ] **Step 2: Commit**

```bash
git add search/engines/dev_vespa.py
git commit -m "feat: populate idx in DevVespaPassageSearchEngine (FUS-48)"
```

---

### Task 3: Populate `idx` in `DevVespaDocumentSearchEngine`'s embedded passages mapping

**Files:**

- Modify: `search/engines/dev_vespa.py` (inside `DevVespaDocumentSearchEngine`,
  find by content match — approx. lines 730-741)

- [ ] **Step 1: Add `idx` to the mapping**

Find this block:

```python
                passages.append(
                    Passage(
                        text_block_id=passage.get("text_block_id", ""),
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

Replace with (only the added `idx=` line changes):

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

Note: check whether the embedded `documents.sd` passage struct (which this
`passage` dict is read from — see `struct passage` in
`vespa/app/schemas/documents.sd`) actually has an `idx` field stored on it. If
it does not, `passage.get("idx", 0)` will just default to `0` for every result —
that's acceptable for this pass (matches the "not all data may be available
everywhere yet" reality), but note it in the commit body if so.

- [ ] **Step 2: Verify it imports cleanly**

Run:
`cd /Users/katy/Code/search && uv run python -c "from search.engines.dev_vespa import DevVespaDocumentSearchEngine"`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add search/engines/dev_vespa.py
git commit -m "feat: populate idx in DevVespaDocumentSearchEngine embedded passages (FUS-48)"
```

---

### Task 4: Update `tests/common_strategies.py` (Hypothesis strategy) to include `idx`

**Files:**

- Modify: `tests/common_strategies.py:125-137`

- [ ] **Step 1: Add `idx` to `passage_data_strategy`**

Find:

```python
@st.composite
def passage_data_strategy(draw) -> dict:
    """Generate input data for Passage model."""
    return {
        "text_block_id": draw(text_block_id_strategy),
        "text": draw(text_strategy),
        "language": draw(st.sampled_from(["en", "fr", "es", "de", "pt"])),
        "type": draw(st.sampled_from(["Text", "Title", "Table", "Figure"])),
        "type_confidence": draw(st.floats(min_value=0.0, max_value=1.0)),
        "page_number": draw(st.integers(min_value=0, max_value=1000)),
        "heading_id": draw(st.one_of(st.none(), text_block_id_strategy)),
        "document_id": draw(document_id_strategy),
    }
```

Replace with (only the added `"idx"` line changes):

```python
@st.composite
def passage_data_strategy(draw) -> dict:
    """Generate input data for Passage model."""
    return {
        "text_block_id": draw(text_block_id_strategy),
        "idx": draw(st.integers(min_value=0, max_value=10000)),
        "text": draw(text_strategy),
        "language": draw(st.sampled_from(["en", "fr", "es", "de", "pt"])),
        "type": draw(st.sampled_from(["Text", "Title", "Table", "Figure"])),
        "type_confidence": draw(st.floats(min_value=0.0, max_value=1.0)),
        "page_number": draw(st.integers(min_value=0, max_value=1000)),
        "heading_id": draw(st.one_of(st.none(), text_block_id_strategy)),
        "document_id": draw(document_id_strategy),
    }
```

- [ ] **Step 2: Run tests using this strategy**

Run: `cd /Users/katy/Code/search && uv run pytest tests/ -k "passage" -v`
Expected: all passing tests referencing
`passage_strategy`/`passage_data_strategy` still PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/common_strategies.py
git commit -m "test: add idx to passage_data_strategy (FUS-48)"
```

---

### Task 5: Add `tokens` field, always request `debug-summary`

**Files:**

- Modify: `search/passage.py`
- Modify: `search/engines/dev_vespa.py` (`DevVespaPassageSearchEngine.search`)

Re-checked against the target Snowflake model
(`pipeline_embeddings_input_with_topics_v2`, all 12 columns) after adding `idx`:
the only remaining gaps are `tokens` and `serialised_text`. `tokens` is
available for free — `vespa/app/schemas/passages.sd`'s `debug-summary` already
defines `summary text_tokens { source: text; tokens }`, currently only requested
when `self.debug` is `True`. `serialised_text` has no data source anywhere in
Vespa, the feed materializer, or the source `TextBlock`/`EmbeddingsInputV2`
types — it's a genuine gap requiring upstream pipeline work and is out of scope
for this plan (flagged as a known follow-up below).

Decision (confirmed with Katy): always request `debug-summary` (accepting its
`from-disk` performance cost for now) rather than adding a new dedicated Vespa
summary — simplest fix, no schema changes.

- [ ] **Step 1: Add `tokens` field to `Passage`**

In `search/passage.py`, add a `tokens: list[str]` field:

```python
from pydantic import BaseModel, Field, computed_field


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
    document_id: str = Field(default="")
    tokens: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id
```

- [ ] **Step 2: Always request `debug-summary` in
      `DevVespaPassageSearchEngine.search`**

Find this block in `search/engines/dev_vespa.py`:

```python
        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
        }
        if self.debug:
            request_body["ranking.profile"] = "nativerank"
            request_body["presentation.summary"] = "debug-summary"
```

Replace with:

```python
        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "presentation.summary": "debug-summary",
        }
        if self.debug:
            request_body["ranking.profile"] = "nativerank"
```

This keeps `ranking.profile: nativerank` debug-only (that one genuinely changes
ranking behavior, not just field visibility) while always requesting the
`debug-summary` document-summary so `text_tokens` is present on every response.

- [ ] **Step 3: Populate `tokens` in the hit-to-Passage mapping**

Find:

```python
        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
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
                    document_id=fields.get("document_id", ""),
                )
            )
```

Replace with:

```python
        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
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
                    document_id=fields.get("document_id", ""),
                    tokens=fields.get("text_tokens") or [],
                )
            )
```

- [ ] **Step 4: Verify imports cleanly and commit**

Run:
`cd /Users/katy/Code/search && uv run python -c "from search.passage import Passage; from search.engines.dev_vespa import DevVespaPassageSearchEngine"`
Expected: no errors.

```bash
git add search/passage.py search/engines/dev_vespa.py
git commit -m "feat: add tokens field, always request debug-summary for text_tokens (FUS-48)"
```

- [ ] **Step 5: Update `tests/common_strategies.py` for `tokens`**

Find in `passage_data_strategy`:

```python
        "heading_id": draw(st.one_of(st.none(), text_block_id_strategy)),
        "document_id": draw(document_id_strategy),
    }
```

Replace with:

```python
        "heading_id": draw(st.one_of(st.none(), text_block_id_strategy)),
        "document_id": draw(document_id_strategy),
        "tokens": draw(st.lists(text_strategy, max_size=5)),
    }
```

Run: `cd /Users/katy/Code/search && uv run pytest tests/ -k "passage" -v`
Expected: same pass/fail counts as before this task — the 2 e2e failures
(`test_passage_imported_principal_id_resolves_to_parent`,
`test_passage_principal_title_resolves_via_principal_document_ref`) are
pre-existing/environmental (require a running local Vespa Docker instance;
confirmed failing identically on the pre-idx baseline), not caused by this
change.

```bash
git add tests/common_strategies.py
git commit -m "test: add tokens to passage_data_strategy (FUS-48)"
```

- [ ] **Step 6: Update the debug CLI to show tokens is no longer debug-gated
      (optional, low priority)**

`scripts/search_debug_clis/passage_search.py` already reads `text_tokens` from
`engine.last_debug_info` only `if debug`. Since `tokens` is now always on the
`Passage` object itself, add a row for it unconditionally:

Find:

```python
        text_display = truncate(passage.text, max_len)
        table.add_row("text", highlight(text_display, words))
```

Replace with:

```python
        text_display = truncate(passage.text, max_len)
        table.add_row("text", highlight(text_display, words))
        if passage.tokens:
            table.add_row("tokens", str(passage.tokens))
```

```bash
git add scripts/search_debug_clis/passage_search.py
git commit -m "fix: show tokens field (now always populated) in debug CLI (FUS-48)"
```

---

### Task 6: Full test suite + manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/katy/Code/search && uv run pytest tests/ -v` Expected: all tests
PASS.

- [ ] **Step 2: Manually verify the live route includes `idx`**

Run: `cd /Users/katy/Code/search && just <local-vespa-dev-command>` (see
`vespa/justfile` for the exact target name), then in a second terminal:

```bash
uv run uvicorn api.main:app --reload --port 8000
curl -s "http://localhost:8000/search/passages?query=climate" | python -m json.tool | head -30
```

Expected: each object in `"results"` now includes an `"idx"` key (an integer,
ideally non-zero for at least some results if the Vespa index has real data),
alongside the existing `text_block_id`, `text`, `language`, `type`,
`type_confidence`, `page_number`, `heading_id`, `document_id`, `id`.

- [ ] **Step 3: Confirm OpenAPI schema reflects the new field**

Run:
`curl -s "http://localhost:8000/search/openapi.json" | python -c "import json,sys; s=json.load(sys.stdin); print(s['components']['schemas']['Passage']['properties'].keys())"`
Expected: keys include `idx` alongside all previously-existing fields.

---

### Out of scope (per ticket + Slack confirmation with Patrick, 2026-07-20)

- Renaming fields to match Snowflake naming (`content`, `content_type`, `pages`
  as an array) — explicitly deferred; current names are fine for this first
  pass.
- `serialised_text` — no data source anywhere in Vespa, the feed materializers,
  or the source `TextBlock`/`EmbeddingsInputV2` types. Would require upstream
  pipeline work before this API layer could surface it.
- `topics`/spans (which topics matched, span offsets) — explicitly out of scope
  per ticket description.
- Document title — explicitly out of scope per ticket description (frontend gets
  this from the contextual layer).
- **`pages` — deliberately left untouched, two real gaps found but not fixed
  here:**
  1. `search/vespa/passages_feed_materializer.py`'s
     `_text_block_to_vespa_update` does not populate `page_number` (or
     `type`/`type_confidence`) into Vespa's `passages` schema at all today —
     meaning `page_number` is always `0` on the live `GET /search/passages`
     route regardless of any API-layer change. This is a pre-existing bug, not
     something FUS-48 introduced.
  2. Both materializers (`passages_feed_materializer.py` if fixed, and the
     existing `documents_feed_materializer.py:373-378`) only ever take
     `block["pages"][0]["number"]` — the first page — discarding any subsequent
     pages when a text block spans multiple pages. The source
     `TextBlock.pages: list[PageRef]` already carries full multi-page data; it's
     just never propagated past the first entry.
  3. Genuinely fixing `pages` as an array (matching the target model's shape)
     requires: a Vespa schema change (`passages.sd`'s `page_number: int` →
     `pages: array<int>` or similar), updating both materializers to populate
     all pages instead of just the first, and a Vespa re-feed for the new field
     to have real data. This is bigger than an API-model change and was
     intentionally deferred — worth its own ticket.

# Search MCP runbook

The search MCP lets Claude search CPR's documents and passages with the same
engines and ranking as the website. It's read-only.

```text
You ask Claude ──▶ Claude picks a tool ──▶ search MCP (api/mcp) ──▶ search engines ──▶ Vespa
```

## Who can use it

| Who       | How                                     | Status                |
| --------- | --------------------------------------- | --------------------- |
| Engineers | Run it locally and connect Claude Code  | Available now         |
| CPR staff | Add it to Claude like the data lake MCP | Coming in a follow-up |

The deployed search API keeps the MCP off for now, because the API is public.

## Use it from Claude

### Connect (engineers, local)

1. Make sure `api/.env` exists. If not, run `cd api && just gen-env`
2. Start the API with the MCP on, `cd api && just dev-mcp`, and leave it running
3. Add it to Claude Code once

   ```sh
   claude mcp add --scope local --transport http cpr-search http://127.0.0.1:8000/search/mcp/
   ```

4. Open a new Claude Code chat, since chats that were already open won't see it
5. Type `/mcp` and check `cpr-search` is connected with 5 tools

`just gen-env` with no instance points at production Vespa. That's safe because
the MCP only reads, but use `just gen-env <instance>` for a dev instance.

### Ask good questions

| Do                                            | Example                                                                             |
| --------------------------------------------- | ----------------------------------------------------------------------------------- |
| Name the country, region or kind of document  | "Find Chile's adaptation policies published since 2019"                             |
| Ask it to quote when you need the exact words | "Quote what the UK Climate Change Act says about carbon budgets"                    |
| Find a document first, then ask about it      | "Find Germany's Federal Climate Change Act, then what it says about sector budgets" |
| Mention CPR's topics for a precise subject    | "Find passages about heat waves in India using CPR's topic tagging"                 |

It's for finding and quoting, not counting. Questions like "how many" or "list
every" should go to the data lake MCP, and Claude will say so.

## Tools

| Tool               | Use it to                                                       | Args                                                                                                                        |
| ------------------ | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `search_documents` | Find laws, policies and cases, one result per law               | `query`, `geographies`, `regions`, `categories`, `response_areas`, `topics`, `published_after`, `published_before`, `limit` |
| `search_passages`  | Find text to quote, across everything or inside given documents | `query`, `document_ids`, `geographies`, `regions`, `categories`, `topics`, `limit`                                          |
| `get_passage`      | Read a passage in full, with the passages either side           | `text_block_id`, `context` (0 to 3, default 1)                                                                              |
| `get_document`     | Look up one document by id                                      | `document_id`                                                                                                               |
| `search_topics`    | Turn a subject into a topic id for the `topics` filter          | `query`, `limit`                                                                                                            |

### Filters

| Arg                                   | Format                                         | Example                  |
| ------------------------------------- | ---------------------------------------------- | ------------------------ |
| `geographies`                         | ISO 3166-1 alpha-3 country codes               | `["KEN", "GBR"]`         |
| `regions`                             | World Bank region names                        | `["Sub-Saharan Africa"]` |
| `categories`                          | One of the 7 categories                        | `["Law", "Policy"]`      |
| `response_areas`                      | One of 4 policy response areas, documents only | `["Adaptation"]`         |
| `topics`                              | Ids from `search_topics`                       | `["concept::Q1343"]`     |
| `published_after`, `published_before` | ISO dates, documents only                      | `"2020-01-01"`           |

- Any value within one filter matches, and different filters must all match
- `document_ids` can't be combined with other filters, because searching within
  documents ORs filters with the query
- A bad value, like a country name instead of a code, gets an error saying how
  to fix it rather than an empty result

### Results

- `limit` defaults to 10 and is capped at 25
- Search tools return `results` and `has_more`. `has_more` means there may be
  more matches, so the count is never a total
- Passages include their law's `document_title`, so Claude can cite them without
  another call
- Passages over 1,500 characters are cut at a sentence end, end in "…" and are
  marked `text_truncated`. `get_passage` returns the full text
- Repeated passages (the same text across a law's versions) and headings, page
  headers and tables of contents are dropped
- `get_document` returns `is_principal`, which is true for a law itself and
  false for one of its versions

## Call a tool directly

This shows the exact JSON Claude gets, with no model involved. Run from the repo
root while `just dev-mcp` is running.

```bash
MCP=http://127.0.0.1:8000/search/mcp/

uv run fastmcp list $MCP
uv run fastmcp call $MCP search_topics query="adaptation finance"
uv run fastmcp call $MCP search_documents \
  --input-json '{"query": "climate change act", "geographies": ["KEN"], "categories": ["Law"]}'
uv run fastmcp call $MCP search_passages \
  --input-json '{"query": "climate change fund", "document_ids": ["CCLW.family.2042.0"]}'
```

Add `--json` for the raw response.

## See what it's doing

The `just dev-mcp` terminal logs one line per tool call. The level matches the
outcome, using the same prefixes as the search API's request log.

| Prefix      | Level   | Means                                                             |
| ----------- | ------- | ----------------------------------------------------------------- |
| `Success:`  | INFO    | The call worked, with its result count                            |
| `Rejected:` | WARNING | Claude's call was wrong, e.g. a bad country code or an unknown id |
| `Error:`    | ERROR   | Search failed, e.g. Vespa is down                                 |

```text
Success: tool call surface=mcp tool=search_documents args={'query': 'climate change act', 'geographies': ['KEN']} duration_ms=101 results=3
Rejected: tool call surface=mcp tool=search_documents args={'geographies': ['Kenya'], ...} duration_ms=2 error=FilterArgError("'Kenya' isn't a country code we have. ...")
```

An `Error:` line logs the real cause, while Claude only gets a fixed message
like "Search is unavailable right now".

## Run the tests

```bash
uv run pytest tests/api/mcp -q
```

They mock Vespa, so they check what each tool sends and returns but not that
Vespa matches the filters. Check new filters live with `fastmcp call`.

## Troubleshooting

| Symptom                                    | Likely cause                                          | Fix                                        |
| ------------------------------------------ | ----------------------------------------------------- | ------------------------------------------ |
| `/mcp` says `cpr-search` failed to connect | The server isn't running                              | Run `just dev-mcp`, then reconnect         |
| Claude doesn't see the tools               | The chat was open before the server started           | Open a new chat                            |
| Claude uses old tool descriptions          | The server wasn't restarted after a change            | Restart `just dev-mcp` and open a new chat |
| A filter returns nothing                   | No matches, or the label isn't on that kind of record | Try the call without the filter            |
| A topic filter misses an obvious result    | Topic tagging isn't complete                          | Try a broader topic, or search without one |
| "Search is unavailable right now"          | Vespa is down or unreachable                          | Check `api/.env` and the `Error:` log line |

## Known gaps

- **Response areas** only work on `search_documents`, because passages don't
  carry them
- **Country groups** like small island states aren't supported, so list their
  codes in `geographies`
- **Passage country and region filters** miss documents whose label uses a
  second name, e.g. "Bolivia, Plurinational State of". This mostly affects
  Bolivia, Moldova and Micronesia, and needs a data fix
- **One fund** (e.g. GCF only) can't be picked, since Multilateral Climate Fund
  project is a single category
- **Sign in** isn't built yet, which is why the MCP is off when deployed

## Where the code is

```text
api/mcp/
├── server.py        build_server() and the 5 tools
├── filters.py       tool args → the engine's filter tree
├── models.py        trims engine results for Claude
├── descriptions.py  everything Claude reads to pick a tool
└── middleware.py    the call log and the error messages Claude sees
api/main.py          mounts the MCP at /search/mcp when MCP_ENABLED=true
api/state.py         the shared HTTP client, read by routes and tools with HttpxDep
tests/api/mcp/       unit tests
```

After changing `descriptions.py`, re-test from a new Claude chat, since that
wording decides which tool Claude picks. `testing-changelog.md` has what each
round of testing found and what changed. Read `docs/errors.md` before changing
any error path.

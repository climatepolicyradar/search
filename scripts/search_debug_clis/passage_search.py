import json

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from api.routers import settings
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DevVespaPassageSearchEngine

app = typer.Typer()
console = Console()


def truncate(s: str, max_len: int | None) -> str:
    s = s.replace("\n", " ↵ ")
    if max_len is not None and len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def highlight(s: str, words: list[str]) -> Text:
    t = Text(s)
    t.highlight_words(words, style="bold yellow", case_sensitive=False)
    return t


def _topic_condition(topic: str) -> dict:
    """One topic condition. A bare wikibase id is given the `concept::` prefix."""
    value = topic if topic.startswith("concept::") else f"concept::{topic}"
    return {"field": "labels.value.id", "op": "contains", "value": value}


def _build_topic_filter(topics: list[str], topic_or: bool) -> dict | None:
    """
    Group the --topic values into a single condition, AND by default, OR with `--or`.

    Each topic sits in its own nested group because topics in a group would get collapsed
    by the engine into a single `sameElement(...)`, so match nothing. See 
    `_build_filter_yql` in `search/engines/dev_vespa.py`.
    """
    if not topics:
        return None
    conditions = [_topic_condition(topic) for topic in topics]
    if topic_or:
        return {"op": "or", "filters": conditions}
    return {
        "op": "and",
        "filters": [{"op": "or", "filters": [condition]} for condition in conditions],
    }


def _build_filters(
    document_id: str | None,
    filters: str | None,
    topics: list[str],
    topic_or: bool,
) -> str | None:
    """Combine the --document-id and --topic shorthand with any raw --filters JSON."""
    conditions: list[dict] = []
    if document_id:
        conditions.append(
            {"field": "document_id", "op": "contains", "value": document_id}
        )
    if topic_filter := _build_topic_filter(topics, topic_or):
        conditions.append(topic_filter)
    if filters:
        conditions.append(json.loads(filters))
    if not conditions:
        return None
    return json.dumps({"op": "and", "filters": conditions})


@app.command()
def search(
    query: str = typer.Argument(
        "", help="Free-text query. Omit for a filter-only search (e.g. --topic/--document-id)."
    ),
    page: int = 1,
    page_size: int = 10,
    debug: bool = True,
    max_len: int | None = 600,
    filters: str | None = None,
    document_id: str | None = None,
    topic: list[str] = typer.Option(
        [],
        "--topic",
        help="Filter to passages tagged with this topic, e.g. Q1653 or "
        "concept::Q1653. Repeatable. Default is to require all of them i.e. AND",
    ),
    topic_or: bool = typer.Option(
        False,
        "--or",
        help="Match passages carrying ANY of the given --topic values. "
        "Default is to require all of them i.e. AND",
    ),
):
    """Search for passages."""
    engine = DevVespaPassageSearchEngine(settings=settings, debug=debug)
    results = engine.search(
        query=query,
        filters_json_string=_build_filters(document_id, filters, topic, topic_or),
        pagination=Pagination(page_token=page, page_size=page_size),
        order_by=[OrderBy(field="relevance", direction="desc")],
    )

    words = query.split()

    for i, passage in enumerate(results.results):
        relevance = None
        summaryfeatures = None
        text_tokens = None
        if debug and i < len(engine.last_debug_info):
            info = engine.last_debug_info[i]
            relevance = info.get("relevance")
            summaryfeatures = info.get("summaryfeatures")
            text_tokens = info.get("text_tokens")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        table.add_row("id", passage.text_block_id)
        table.add_row("document_id", passage.document_id)
        table.add_row("type", passage.type)
        table.add_row("type_confidence", str(passage.type_confidence))
        table.add_row("language", passage.language)
        if passage.pages:
            table.add_row("pages", str(passage.pages))
        if passage.heading_id:
            table.add_row("heading_id", passage.heading_id)
        if passage.heading_text:
            table.add_row("heading_text", passage.heading_text)
        passage_topics = [
            label for label in passage.labels if label.value.type == "concept"
        ]
        if passage_topics:
            table.add_row(
                "topics",
                truncate(
                    ", ".join(
                        f"{label.value.value} ({label.value.id})"
                        for label in passage_topics
                    ),
                    max_len,
                ),
            )
        text_display = truncate(passage.text, max_len)
        table.add_row("text", highlight(text_display, words))
        if passage.tokens:
            table.add_row("tokens", str(passage.tokens))
        if relevance is not None:
            table.add_row("relevance", str(relevance))
        if text_tokens:
            table.add_row("text_tokens", truncate(str(text_tokens), max_len))

        parts: list[Table | Syntax] = [table]
        if summaryfeatures:
            parts.append(
                Syntax(
                    json.dumps(summaryfeatures, indent=2, default=str),
                    "json",
                    theme="monokai",
                )
            )

        panel = Panel(Group(*parts), title=f"[bold]#{i + 1}[/bold]")
        console.print(panel)


if __name__ == "__main__":
    app()

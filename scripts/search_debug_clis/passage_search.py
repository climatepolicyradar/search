import json

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from api.dev import settings
from search.engines import Pagination
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


@app.command()
def search(
    query: str,
    page: int = 1,
    page_size: int = 10,
    debug: bool = True,
    max_len: int | None = 600,
):
    """Search for passages."""
    engine = DevVespaPassageSearchEngine(settings=settings, debug=debug)
    results = engine.search(
        query=query,
        pagination=Pagination(page_token=page, page_size=page_size),
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
        if passage.page_number:
            table.add_row("page_number", str(passage.page_number))
        if passage.heading_id:
            table.add_row("heading_id", passage.heading_id)
        text_display = truncate(passage.text, max_len)
        table.add_row("text", highlight(text_display, words))
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

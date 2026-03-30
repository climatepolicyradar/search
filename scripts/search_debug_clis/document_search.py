import json

import typer
from pydantic_settings import SettingsConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from search.engines import Pagination
from search.engines.dev_vespa import DevVespaDocumentSearchEngine, Settings

app = typer.Typer()
console = Console()


class EnvSettings(Settings):
    model_config = SettingsConfigDict(env_file="api/.env")


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]


@app.command()
def search(
    query: str,
    pagination: Pagination = Pagination(page_token=1, page_size=10),
    debug: bool = True,
    filters: str | None = None,
    labels: bool = False,
):
    """Search for documents."""
    engine = DevVespaDocumentSearchEngine(settings=settings, debug=debug)
    results = engine.search(
        query=query,
        filters_json_string=filters,
        pagination=pagination,
    )

    words = query.split()

    def highlight(s: str) -> Text:
        """Return a Text object with query words highlighted."""
        t = Text(s)
        t.highlight_words(words, style="bold yellow", case_sensitive=False)
        return t

    for i, doc in enumerate(results.results):
        relevance = None
        summaryfeatures = None
        geographies = None
        if debug and i < len(engine.last_debug_info):
            info = engine.last_debug_info[i]
            relevance = info.get("relevance")
            summaryfeatures = info.get("summaryfeatures")
            geographies = info.get("geographies")

        # Header table with core fields
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        table.add_row("id", doc.id)
        table.add_row("title", highlight(doc.title))
        if doc.description:
            table.add_row("description", highlight(doc.description))
        if doc.attributes:
            table.add_row("attributes", json.dumps(doc.attributes, default=str))
        if geographies:
            table.add_row("geographies", highlight(", ".join(geographies)))
        if relevance is not None:
            table.add_row("relevance", str(relevance))

        if labels and doc.labels:
            label_strs = [f"{lr.type}: {lr.value.value}" for lr in doc.labels]
            table.add_row("labels", ", ".join(label_strs))

        from rich.console import Group

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

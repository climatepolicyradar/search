import json

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from search.engines import Pagination
from search.engines.dev_vespa import DevVespaLabelSearchEngine

app = typer.Typer()
console = Console()


@app.command()
def search(
    query: str,
    page: int = 1,
    page_size: int = 10,
    debug: bool = True,
    label_type: str | None = None,
):
    """Search for labels."""
    engine = DevVespaLabelSearchEngine(debug=debug)
    results = engine.search(
        query=query,
        pagination=Pagination(page_token=page, page_size=page_size),
        label_type=label_type,
    )

    words = query.split()

    def highlight(s: str) -> Text:
        """Return a Text object with query words highlighted."""
        t = Text(s)
        t.highlight_words(words, style="bold yellow", case_sensitive=False)
        return t

    for i, label in enumerate(results):
        relevance = None
        summaryfeatures = None
        value = ""
        alternative_labels: list[str] = []
        description = ""
        if debug and i < len(engine.last_debug_info):
            info = engine.last_debug_info[i]
            relevance = info.get("relevance")
            summaryfeatures = info.get("summaryfeatures")
            value = info.get("value", "")
            alternative_labels = info.get("alternative_labels", [])
            description = info.get("description", "")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        table.add_row("id", label.id)
        table.add_row("type", label.type)
        if value:
            table.add_row("value", highlight(value))
        if alternative_labels:
            table.add_row(
                "alternative_labels",
                highlight(", ".join(alternative_labels)),
            )
        if description:
            table.add_row("description", highlight(description))
        if relevance is not None:
            table.add_row("relevance", str(relevance))

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

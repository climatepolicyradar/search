import json

import typer
from pydantic_settings import SettingsConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from search.bolding import bolding_to_labels
from search.engines import OrderBy, Pagination
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
    page_token: int = 1,
    page_size: int = 10,
    debug: bool = True,
    filters: str | None = None,
    labels: bool = False,
    topic: str | None = typer.Option(None, "--topic", help="e.g. Q1234 or concept::Q1234"),
    exact_weight: float | None = typer.Option(
        None,
        "--exact-weight",
        help="Exact-form boost weight. Omit for the engine default (1.0); 0 turns it off.",
    ),
):
    """Search for documents."""
    conditions: list[dict] = []
    if topic:
        value = topic if topic.startswith("concept::") else f"concept::{topic}"
        conditions.append({"field": "labels.value.id", "op": "contains", "value": value})
    if filters:
        conditions.append(json.loads(filters))
    filters_json = json.dumps({"op": "and", "filters": conditions}) if conditions else None

    engine_kwargs = {} if exact_weight is None else {"exact_weight": exact_weight}
    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=True, **engine_kwargs
    )
    results = engine.search(
        query=query,
        filters_json_string=filters_json,
        pagination=Pagination(page_token=page_token, page_size=page_size),
        order_by=[OrderBy(field="relevance", direction="desc")],
    )
    console.print(
        f"[bold magenta]{query!r}  {engine.parameters}  total={results.total_size}[/bold magenta]"
    )

    def bolded(s: str) -> Text:
        """`s` with Vespa's <hi> spans styled, exactly as the frontend highlights them."""
        parsed = bolding_to_labels(s)
        t = Text(parsed.text)
        for b in parsed.boldings:
            t.stylize("bold yellow", b.start_index, b.end_index)
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
        table.add_row("title", bolded(doc.title))
        if doc.description:
            table.add_row("description", bolded(doc.description))
        if doc.attributes:
            table.add_row("attributes", json.dumps(doc.attributes, default=str))
        if geographies:
            table.add_row("geographies", ", ".join(geographies))
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

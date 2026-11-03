import asyncio
import json

import httpx2
import typer
from pydantic_settings import SettingsConfigDict
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from search.data_in_models import Document
from search.engines import ListResponse, OrderBy, Pagination
from search.engines.dev_vespa import DevVespaPrincipalDocumentSearchEngine, Settings

app = typer.Typer()
console = Console()


class EnvSettings(Settings):
    model_config = SettingsConfigDict(env_file="api/.env")


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]


async def _run_search(
    query: str,
    page_token: int,
    page_size: int,
    debug: bool,
    bolding: bool,
) -> tuple[ListResponse[Document], list[dict]]:
    async with httpx2.AsyncClient() as httpx_client:
        engine = DevVespaPrincipalDocumentSearchEngine(
            settings=settings, httpx=httpx_client, debug=debug, bolding=bolding
        )
        results = await engine.asearch(
            query=query,
            pagination=Pagination(page_token=page_token, page_size=page_size),
            order_by=[OrderBy(field="relevance", direction="desc")],
        )
        return results, engine.last_debug_info


@app.command()
def search(
    query: str,
    page_token: int = 1,
    page_size: int = 10,
    debug: bool = True,
    bolding: bool = False,
):
    """Search for principal documents."""
    results, last_debug_info = asyncio.run(
        _run_search(query, page_token, page_size, debug, bolding)
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
        if debug and i < len(last_debug_info):
            info = last_debug_info[i]
            relevance = info.get("relevance")
            summaryfeatures = info.get("summaryfeatures")
            geographies = info.get("geographies")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        table.add_row("id", doc.id)
        table.add_row("title", highlight(doc.title))
        if doc.description:
            table.add_row("description", highlight(doc.description))
        if doc.attributes:
            table.add_row(
                "attributes", highlight(json.dumps(doc.attributes, default=str))
            )
        if geographies:
            table.add_row("geographies", highlight(", ".join(geographies)))
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

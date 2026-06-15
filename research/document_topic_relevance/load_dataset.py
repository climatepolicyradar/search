import argparse
from pathlib import Path

import pandas as pd
from pydantic import AnyHttpUrl
from rich.console import Console
from rich.table import Table
from vespa.application import Vespa

from research.document_topic_relevance.src.models import (
    EvalExample,
    PredictorInput,
    Score,
    TopicCorpusStats,
    TopicMentions,
)
from research.document_topic_relevance.src.snowflake_client import (
    connect,
    fetch_topic_corpus_stats,
    fetch_topic_mentions,
)
from search.document import Document
from search.label import Label

console = Console()


def load_evaluation_dataset(path: str) -> list[tuple[str, str, Score]]:
    """Load CSV into (document_id, topic_id, score) tuples, skipping missing scores."""
    df = pd.read_csv(path)
    label_cols = [c for c in df.columns if "|Q" in c]
    melted = df.melt(
        id_vars="DOCUMENT_ID",
        value_vars=label_cols,
        var_name="label",
        value_name="score",
    ).dropna(subset=["score"])
    melted["label"] = melted["label"].str.split("|").str[-1]

    len_before = len(melted)
    melted["score"] = pd.to_numeric(melted["score"], errors="coerce")
    melted = melted.dropna(subset=["score"]).copy()
    skipped = len_before - len(melted)
    if skipped > 0:
        console.log(f"[yellow]Skipped {skipped} rows with non-integer scores[/yellow]")

    melted["score"] = melted["score"].astype(int)
    return list(melted.itertuples(index=False, name=None))


def load_enriched_dataset_from_jsonl(path: str) -> list[EvalExample]:
    """Load the enriched JSONL produced by this script's __main__ into EvalExamples."""
    out: list[EvalExample] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(EvalExample.model_validate_json(line))
    return out


def get_document(client: Vespa, document_id: str) -> Document | None:
    """Fetch a Document from Vespa by its original document ID, or None if missing."""
    console.log(f"📄 Fetching document [bold]{document_id}[/bold]")
    try:
        response = client.get_data(
            schema="documents", data_id=document_id, namespace="documents"
        )
        if response.json.get("pathId") and "fields" not in response.json:
            console.log(f"[yellow]Document not found: {document_id}[/yellow]")
            return None
        fields = response.json["fields"]
    except Exception as e:
        console.log(f"[yellow]Failed to fetch document {document_id}: {e}[/yellow]")
        return None
    return Document(
        title=fields.get("title", ""),
        description=fields.get("description", ""),
        source_url=AnyHttpUrl(
            "https://app.climatepolicyradar.org/FIXME"
        ),  # not stored in schema
        original_document_id=document_id,
        labels=[label["id"] for label in fields.get("labels", [])]
        + [concept["id"] for concept in fields.get("concepts", [])],
    )


def get_label(client: Vespa, label_id: str) -> Label | None:
    """Fetch a Label from Vespa by its label ID, or None if missing."""
    console.log(f"🏷️  Fetching label [bold]{label_id}[/bold]")
    try:
        response = client.get_data(
            schema="labels", data_id=f"concept::{label_id}", namespace="labels"
        )
        if response.json.get("pathId") and "fields" not in response.json:
            console.log(f"[yellow]Label not found: {label_id}[/yellow]")
            return None
        fields = response.json["fields"]
    except Exception as e:
        console.log(f"[yellow]Failed to fetch label {label_id}: {e}[/yellow]")
        return None
    return Label(
        id=fields.get("id", ""),
        type=fields.get("type", ""),
        value=fields.get("value", ""),
        alternative_labels=fields.get("alternative_labels", []),
        subconcept_labels=fields.get("subconcept_labels", []),
        description=fields.get("description", ""),
        negative_labels=fields.get("negative_labels", []),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load and preview an evaluation dataset"
    )
    parser.add_argument("csv", help="Path to the evaluation CSV file")
    parser.add_argument(
        "--vespa-url", default="http://localhost", help="Vespa base URL"
    )
    parser.add_argument("--vespa-port", type=int, default=8080, help="Vespa port")
    parser.add_argument(
        "--skip-snowflake",
        action="store_true",
        help="Skip Snowflake enrichment; mentions are left empty.",
    )
    args = parser.parse_args()

    output_path = Path(__file__).parent / Path("data/dataset.jsonl")

    client = Vespa(url=args.vespa_url, port=args.vespa_port)
    console.log(f"🔌 Connected to Vespa at {args.vespa_url}:{args.vespa_port}")

    dataset = load_evaluation_dataset(args.csv)
    console.log(
        f"📋 Loaded {len(dataset)} labelled entries from [bold]{args.csv}[/bold]"
    )

    unique_document_ids = list(set(document_id for document_id, _, _ in dataset))
    documents_by_id: dict[str, Document | None] = {
        document_id: get_document(client, document_id)
        for document_id in unique_document_ids
    }

    unique_label_ids = list(set(label_id for _, label_id, _ in dataset))
    labels_by_id: dict[str, Label | None] = {
        label_id: get_label(client, label_id) for label_id in unique_label_ids
    }

    # Enrich each (document, topic) pair with passage-level mentions from Snowflake,
    # keyed by (document_id, lower(trim(topic name))). Topics are joined by their
    # human-readable value, which matches the warehouse's TOPIC_NAME.
    mentions_by_pair: dict[tuple[str, str], TopicMentions] = {}
    corpus_stats_by_topic: dict[str, TopicCorpusStats] = {}
    if args.skip_snowflake:
        console.log("[yellow]Skipping Snowflake enrichment (--skip-snowflake)[/yellow]")
    else:
        topic_names = [
            label.value for label in labels_by_id.values() if label and label.value
        ]
        console.log("❄️  Fetching topic mentions from Snowflake")
        conn = connect()
        try:
            mentions_by_pair = fetch_topic_mentions(
                conn, unique_document_ids, topic_names
            )
            console.log("❄️  Fetching corpus-wide topic frequencies from Snowflake")
            corpus_stats_by_topic = fetch_topic_corpus_stats(conn, topic_names)
        finally:
            conn.close()
        console.log(f"❄️  Got mentions for {len(mentions_by_pair)} document-topic pairs")
        missing_corpus = sorted(
            name.lower().strip()
            for name in topic_names
            if name.lower().strip() not in corpus_stats_by_topic
        )
        if missing_corpus:
            console.log(
                f"[yellow]No corpus stats for {len(missing_corpus)} topic(s): "
                f"{', '.join(missing_corpus)}[/yellow]"
            )

    table = Table(title="Evaluation dataset", show_lines=True)
    table.add_column("Document", style="cyan")
    table.add_column("Label", style="magenta")
    table.add_column("Score", justify="right")

    written = 0
    skipped = 0
    with open(output_path, "w") as f:
        for document_id, label_id, score in dataset:
            document = documents_by_id[document_id]
            label = labels_by_id[label_id]

            if document is None:
                console.log(
                    f"[yellow]Skipping entry: missing document {document_id}[/yellow]"
                )
                skipped += 1
                continue
            if label is None:
                console.log(
                    f"[yellow]Skipping entry: missing label {label_id}[/yellow]"
                )
                skipped += 1
                continue

            topic_key = label.value.lower().strip()
            mentions = mentions_by_pair.get(
                (document_id, topic_key),
                TopicMentions(total_passages=0),
            )
            example = EvalExample(
                input=PredictorInput(
                    document=document,
                    topic=label,
                    mentions=mentions,
                    topic_corpus=corpus_stats_by_topic.get(topic_key),
                ),
                score=score,
            )
            f.write(example.model_dump_json() + "\n")
            written += 1
            table.add_row(
                document.title or document_id, label.value or label_id, str(score)
            )

    console.log(
        f"✅ Wrote {written} entries to [bold]{output_path}[/bold]"
        + (f" ([yellow]{skipped} skipped[/yellow])" if skipped else "")
    )
    console.print(table)

import argparse
import json
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table
from src.models import Score
from vespa.application import Vespa

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
    melted = melted[pd.to_numeric(melted["score"], errors="coerce").notnull()].copy()
    skipped = len_before - len(melted)
    if skipped > 0:
        console.log(f"[yellow]Skipped {skipped} rows with non-integer scores[/yellow]")

    melted["score"] = melted["score"].astype(int)
    return list(melted.itertuples(index=False, name=None))


def load_enriched_dataset_from_jsonl(path: str) -> list[tuple[Document, Label, Score]]:
    """Load the enriched JSONL produced by this script's __main__ into tuples."""
    out: list[tuple[Document, Label, Score]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out.append(
                (
                    Document.model_validate(row["document"]),
                    Label.model_validate(row["topic"]),
                    row["score"],
                )
            )
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
        source_url="https://app.climatepolicyradar.org/FIXME",  # not stored in schema
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

            f.write(
                json.dumps(
                    {
                        "document": document.model_dump(mode="json"),
                        "topic": label.model_dump(mode="json"),
                        "score": score,
                    }
                )
                + "\n"
            )
            written += 1
            table.add_row(
                document.title or document_id, label.value or label_id, str(score)
            )

    console.log(
        f"✅ Wrote {written} entries to [bold]{output_path}[/bold]"
        + (f" ([yellow]{skipped} skipped[/yellow])" if skipped else "")
    )
    console.print(table)

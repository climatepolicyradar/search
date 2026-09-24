"""Helpers shared by more than one dev-Vespa search engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from search.data_in_models import Label as DataInLabel
from search.data_in_models import LabelRelationship
from search.engines.vespa_query.client import Settings

# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


class CountAggregation[T](BaseModel):
    count: int
    value: T


def get_labels_from_vespa_response(
    source: dict[str, Any],
    fields: dict[str, Any],
) -> list[LabelRelationship]:
    """
    Build a document's labels from a Vespa response.

    `labels` is a concatenation of document_source.labels and concepts.
    """
    labels: list[LabelRelationship] = []
    for label in source.get("labels", []):
        labels.append(
            LabelRelationship(
                type=label.get("type", MISSING_PLACEHOLDER),
                value=DataInLabel(
                    id=label.get("value").get("id", MISSING_PLACEHOLDER),
                    value=label.get("value").get("value", MISSING_PLACEHOLDER),
                    type=label.get("value").get("type", MISSING_PLACEHOLDER),
                ),
                timestamp=label.get("timestamp"),
            )
        )

    for concept in fields.get("concepts", []):
        labels.append(
            LabelRelationship(
                type="concept",
                value=DataInLabel(
                    id=concept.get("id", MISSING_PLACEHOLDER),
                    type="concept",
                    value=concept.get("value", MISSING_PLACEHOLDER),
                ),
                passages_id=None,
                count=concept.get("count", MISSING_PLACEHOLDER),
            )
        )

    return labels


class DevVespaInstanceAddIn:
    """Surfaces the personal dev instance name (from settings) onto the engine id/config."""

    settings: "Settings"

    @property
    def instance_name(self) -> str | None:
        """Name of the specific instance of the search engine"""
        return self.settings.vespa_dev_instance_name

from collections import Counter
from typing import TypedDict


class InferenceResult(TypedDict):
    id: str
    name: str
    parent_concepts: list[str]
    parent_concept_ids_flat: str
    model: str
    end: int
    start: int
    timestamp: str


InferenceResultInput = dict[str, list[InferenceResult]]


# This matches concept in `search.models.Concept`
class VespaLabelField(TypedDict):
    id: str
    type: str
    value: str
    # 👇 These are experimental  and should not be relied on
    passages_id: str | None
    count: int | None


class VespaAssign[T](TypedDict):
    assign: T


class VespaUpdate(TypedDict):
    update: str
    fields: dict[str, VespaAssign[list[VespaLabelField]]]


def index(
    document_id: str, inference_results_input: InferenceResultInput
) -> VespaUpdate:
    concept_counts: Counter[str] = Counter()
    concept_names: dict[str, str] = {}
    concept_passages: dict[str, list[str]] = {}
    for passage_id, concept_list in inference_results_input.items():
        for concept in concept_list:
            concept_counts[concept["id"]] += 1
            concept_names[concept["id"]] = concept["name"]
            concept_passages.setdefault(concept["id"], []).append(passage_id)

    inference_results: list[VespaLabelField] = [
        {
            "id": concept_id,
            "type": "concept",
            "value": concept_names[concept_id],
            "count": count,
            "passages_id": "::".join(concept_passages[concept_id]),
        }
        for concept_id, count in concept_counts.items()
    ]

    update_op: VespaUpdate = {
        "update": f"id:documents:documents::{document_id}",
        "fields": {
            "concepts": {"assign": inference_results},
        },
    }

    return update_op

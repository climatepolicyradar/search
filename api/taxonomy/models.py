from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from api.geographies_taxonomy import geographies_taxonomy
from api.labels_taxonomy import labels_taxonomy
from search.data_in_models import Label
from search.label import LabelSearchResult


class TaxonomyNode(BaseModel):
    id: str
    type: str
    value: str
    alternative_labels: list[str]
    count: int
    children: list["TaxonomyNode"]


taxonomy: list[Label] = [
    *geographies_taxonomy,
    *labels_taxonomy,
]



def _as_search_result(label: Label) -> LabelSearchResult:
    return LabelSearchResult(
        id=label.id,
        type=label.type,
        value=label.value,
        labels=label.labels,
    )


def merge(
    hardcoded: Sequence[Label],
    fetched: Sequence[LabelSearchResult],
) -> list[LabelSearchResult]:
    """Combine the hardcoded taxonomy with fetched labels, hardcoded winning an id clash."""
    labels_by_id: dict[str, LabelSearchResult] = {
        label.id: _as_search_result(label) for label in hardcoded
    }

    for label in fetched:
        labels_by_id.setdefault(label.id, label)

    return list(labels_by_id.values())


@dataclass
class LabelNode:
    id: str
    type: str
    value: str
    is_root: bool
    children: list["LabelNode"]
    alternative_labels: list[str]

    def types(self) -> set[str]:
        """Return every label type in this subtree."""
        return {self.type}.union(*(child.types() for child in self.children))

    def ids(self) -> set[str]:
        """Return every label id in this subtree."""
        return {self.id}.union(*(child.ids() for child in self.children))

    def has_child(self, child_id: str) -> bool:
        """Does a label with the given ID appear anywhere in this subtree?"""
        return self.id == child_id or any(child.has_child(child_id) for child in self.children)

    def find(self, label_types: set[str], label_ids: set[str]) -> list["LabelNode"]:
        """Return the highest nodes in this subtree whose type or id was asked for."""
        if self.type in label_types or self.id in label_ids:
            return [self]

        return [
            found
            for child in self.children
            for found in child.find(label_types, label_ids)
        ]

    def response(self, counts: dict[str, int]) -> TaxonomyNode:
        """Convert this subtree to the API response model, counted from `counts`."""
        return TaxonomyNode(
            id=self.id,
            type=self.type,
            value=self.value,
            count=counts.get(self.id, 0),
            alternative_labels=self.alternative_labels,
            children=[child.response(counts) for child in self.children],
        )



def tree(labels: Sequence[LabelSearchResult]) -> list[LabelNode]:
    """Build the whole label tree, returning its roots."""
    nodes_by_id: dict[str, LabelNode] = {}

    def node_for(label: LabelSearchResult) -> LabelNode:
       if label.id in nodes_by_id:
           existing = nodes_by_id[label.id]
           alternatives = [*existing.alternative_labels, *label.alternative_labels]
           existing.alternative_labels = list(dict.fromkeys(alternatives))
           return existing

       node = LabelNode(
           id=label.id,
           type=label.type,
           value=label.value,
           alternative_labels=list(dict.fromkeys(label.alternative_labels)),
           is_root=True,
           children=[],
        )

       nodes_by_id[label.id] = node
       return node

    for label in labels:
        child = node_for(label)
        for parent_label in label.labels:
            if parent_label.type == "subconcept_of" and not child.has_child(parent_label.value.id):
                parent = node_for(_as_search_result(parent_label.value))
                parent.children.append(child)
                child.is_root = False

    return [node for node in nodes_by_id.values() if node.is_root]


def select(
    roots: Sequence[LabelNode],
    subtrees: list[str] | None,
    ids: list[str] | None,
) -> list[LabelNode]:
    """Return `roots`, or the highest nodes beneath them of the given types or ids."""
    if subtrees is None and ids is None:
        return list(roots)

    selected = list({
        found.id: found
        for root in roots
        for found in root.find(set(subtrees or []), set(ids or []))
    }.values())

    nested = {
        descendant
        for node in selected
        for descendant in node.ids()
        if descendant != node.id
    }

    return [node for node in selected if node.id not in nested]

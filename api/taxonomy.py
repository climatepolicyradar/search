from collections.abc import Sequence
from dataclasses import dataclass

from api.geographies_taxonomy import geographies_taxonomy
from api.labels_taxonomy import labels_taxonomy
from api.models import TaxonomyNode
from search.data_in_models import Label
from search.label import LabelSearchResult

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
    by_id: dict[str, LabelSearchResult] = {
        label.id: _as_search_result(label) for label in hardcoded
    }

    for label in fetched:
        by_id.setdefault(label.id, label)

    return list(by_id.values())


@dataclass
class LabelNode:
    id: str
    type: str
    value: str
    count: int 
    is_root: bool
    children: list["LabelNode"]
    alternative_labels: list[str]

    def types(self) -> set[str]:
        """Return every label type in this subtree."""
        return {self.type}.union(*(child.types() for child in self.children))

    def ids(self) -> set[str]:
        """Return every label id in this subtree."""
        return {self.id}.union(*(child.ids() for child in self.children))

    def find(self, types: set[str]) -> list["LabelNode"]:
        """Return the highest nodes in this subtree whose type is in `types`."""
        if self.type in types:
            return [self]

        return [
            found
            for child in self.children
            for found in child.find(types)
        ]

    def set_count(self, counts: dict[str, int]) -> None:
        """Set each node's count in this subtree from `counts`, keyed by label id."""
        self.count = counts.get(self.id, 0)
        for child in self.children:
            child.set_count(counts)

    def response(self) -> TaxonomyNode:
        """Convert this subtree to the API response model."""
        return TaxonomyNode(
            id=self.id,
            type=self.type,
            value=self.value,
            count=self.count,
            alternative_labels=self.alternative_labels,
            children=[child.response() for child in self.children],
        )
   


def tree(
    input: Sequence[LabelSearchResult],
    subtrees: list[str] | None,
) -> list[LabelNode]:
    by_id: dict[str, LabelNode] = {}

    def node(label: LabelSearchResult) -> LabelNode:
       if label.id in by_id:
           existing = by_id[label.id]
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
           count=0, 
        )

       by_id[label.id] = node
       return node

    for label in input:
        us = node(label)
        for parent_label in label.labels:
            if parent_label.type == "subconcept_of":
                parent = node(_as_search_result(parent_label.value))
                parent.children.append(us)
                us.is_root = False

    roots = [n for n in by_id.values() if n.is_root]
    if subtrees is None:
        return roots

    return list({
        match.id: match
        for root in roots
        for match in root.find(set(subtrees))
    }.values())

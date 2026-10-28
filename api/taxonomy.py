from dataclasses import dataclass

from api.geographies_taxonomy import geographies_taxonomy
from api.labels_taxonomy import labels_taxonomy
from api.models import TaxonomyNode
from search.data_in_models import Label

taxonomy: list[Label] = [
    *geographies_taxonomy, 
    *labels_taxonomy,
]



@dataclass
class LabelNode:
    id: str
    type: str
    value: str
    count: int 
    is_root: bool
    children: list["LabelNode"]

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
            children=[child.response() for child in self.children],
        )
   


def tree(input: list[Label], subtrees: list[str] | None) -> list[LabelNode]:
    by_id: dict[str, LabelNode] = {}

    def node(label: Label) -> LabelNode:
       if label.id in by_id:
           return by_id[label.id]

       node = LabelNode(
           id=label.id, 
           type=label.type, 
           value=label.value, 
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
                parent = node(parent_label.value)
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

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

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


@dataclass(frozen=True)
class LabelPath:
    """Where a node sits: the ids from a root down to it."""

    ids: tuple[str, ...] = ()

    def then(self, label_id: str) -> "LabelPath":
        """Return this path extended by one step."""
        return LabelPath((*self.ids, label_id))


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

    def _matches(self, glob: str) -> bool:
        return fnmatch.fnmatchcase(self.id, glob)

    def find_path(
        self,
        path: PurePosixPath,
        ancestry: LabelPath = LabelPath(),
    ) -> list[LabelPath]:
        """
        Return where the nodes beneath here whose path matches `path` sit.

        A node reachable from several parents sits at several paths, and only the
        matching ones are returned - so the id alone cannot stand in for the path.
        """
        parts = path.parts
        if not parts:
            return []

        here = ancestry.then(self.id)
        rest = PurePosixPath(*parts[1:])
        head = parts[0]

        if head == "**":
            found = [here] if not rest.parts else self.find_path(rest, ancestry)
            return found + [
                match
                for child in self.children
                for match in child.find_path(path, here)
            ]

        if not self._matches(head):
            return []

        if not rest.parts:
            return [here]

        if rest.parts[0] == "**":
            return self.find_path(rest, ancestry)

        return [
            match
            for child in self.children
            for match in child.find_path(rest, here)
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


def _pruned(
    node: LabelNode,
    ancestry: LabelPath,
    selected: set[LabelPath],
) -> LabelNode | None:
    here = ancestry.then(node.id)
    children = [
        kept
        for kept in (_pruned(child, here, selected) for child in node.children)
        if kept is not None
    ]

    if here not in selected and not children:
        return None

    return LabelNode(
        id=node.id,
        type=node.type,
        value=node.value,
        is_root=node.is_root,
        children=children,
        alternative_labels=node.alternative_labels,
    )


def select(
    roots: Sequence[LabelNode],
    patterns: list[str] | None,
) -> list[LabelNode]:
    """Return `roots`, or the smallest tree holding every node matching `patterns`."""
    if patterns is None:
        return list(roots)

    selected = {
        found
        for pattern in patterns
        for root in roots
        for found in root.find_path(PurePosixPath(pattern))
    }

    return [
        kept
        for kept in (_pruned(root, LabelPath(), selected) for root in roots)
        if kept is not None
    ]

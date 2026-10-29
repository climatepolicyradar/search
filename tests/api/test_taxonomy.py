from api.taxonomy import LabelNode, merge, tree
from search.data_in_models import Label, LabelRelationship
from search.label import LabelSearchResult

REGION = Label(id="region::SA", type="region", value="South America", labels=[])
VESPA_NAME = "Bolivia, Plurinational State of"
HARDCODED_NAME = "Bolivia"


def _parented(id: str, type: str, value: str, parents: list[Label]) -> Label:
    return Label(
        id=id,
        type=type,
        value=value,
        labels=[
            LabelRelationship(type="subconcept_of", value=parent) for parent in parents
        ],
    )


def _country(value: str) -> Label:
    return _parented("country::BOL", "country", value, [REGION])


def _fetched(label: Label, alternative_labels: list[str] | None = None) -> LabelSearchResult:
    return LabelSearchResult.model_validate(
        {**label.model_dump(), "alternative_labels": alternative_labels or []}
    )


def _by_id(nodes: list[LabelNode]) -> dict[str, LabelNode]:
    return {node.id: node for node in nodes}


def test_hardcoded_wins_a_value_collision() -> None:
    merged = merge([REGION, _country(HARDCODED_NAME)], [_fetched(_country(VESPA_NAME))])
    values = [label.value for label in merged if label.id == "country::BOL"]
    assert values == [HARDCODED_NAME]


def test_an_edge_in_both_sources_links_the_child_once() -> None:
    merged = merge([REGION, _country(HARDCODED_NAME)], [_fetched(_country(VESPA_NAME))])
    region = _by_id(tree(merged, None))["region::SA"]
    assert [child.id for child in region.children] == ["country::BOL"]


def test_a_fetched_child_attaches_to_its_hardcoded_parent() -> None:
    subdivision = _parented(
        "subdivision::BO-X", "subdivision", "Somewhere", [_country(VESPA_NAME)]
    )
    merged = merge([REGION, _country(HARDCODED_NAME)], [_fetched(subdivision)])
    country = _by_id(tree(merged, None))["region::SA"].children[0]
    assert country.value == HARDCODED_NAME
    assert [child.id for child in country.children] == ["subdivision::BO-X"]


def test_a_label_only_vespa_knows_about_is_kept() -> None:
    keyword = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    merged = merge([REGION], [_fetched(keyword, ["Flooding"])])
    assert "keyword::Flood" in _by_id(tree(merged, None))


def test_alternative_labels_survive_onto_the_node() -> None:
    keyword = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    merged = merge([REGION], [_fetched(keyword, ["Flooding", "Inundation"])])
    node = _by_id(tree(merged, None))["keyword::Flood"]
    assert node.alternative_labels == ["Flooding", "Inundation"]


def test_a_hardcoded_label_has_no_alternative_labels() -> None:
    node = _by_id(tree(merge([REGION], []), None))["region::SA"]
    assert node.alternative_labels == []


def _concept(id: str, alternative_labels: list[str], parent: str | None = None) -> LabelSearchResult:
    parents = [Label(id=parent, type="concept", value="Flooding")] if parent else []
    return _fetched(
        _parented(id, "concept", "Flooding", parents), alternative_labels
    )


def test_a_parent_seen_first_as_a_relationship_keeps_its_alternative_labels() -> None:
    parent = _concept("concept::Q1", ["inundation", "flood"])
    child = _concept("concept::Q2", ["flash flooding"], parent="concept::Q1")
    nodes = _by_id(tree(merge([], [child, parent]), None))
    assert nodes["concept::Q1"].alternative_labels == ["inundation", "flood"]


def test_alternative_labels_are_deduped() -> None:
    parent = _concept("concept::Q1", ["inundation", "flood", "inundation"])
    child = _concept("concept::Q2", ["flash flooding"], parent="concept::Q1")
    nodes = _by_id(tree(merge([], [child, parent]), None))
    assert nodes["concept::Q1"].alternative_labels == ["inundation", "flood"]


def test_a_label_with_two_parents_hangs_under_both() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    both = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    nodes = _by_id(tree(merge([law, policy], [_fetched(both)]), None))
    assert [child.id for child in nodes["category::Law"].children] == ["concept::Q1"]
    assert [child.id for child in nodes["category::Policy"].children] == ["concept::Q1"]
    assert nodes["category::Law"].children[0] is nodes["category::Policy"].children[0]


def test_a_parent_absent_from_the_input_is_still_built_from_the_relationship() -> None:
    orphan = _parented(
        "concept::Q2",
        "concept",
        "Flash flood",
        [Label(id="concept::Q1", type="concept", value="Flooding", labels=[])],
    )
    nodes = _by_id(tree(merge([], [_fetched(orphan)]), None))
    assert list(nodes) == ["concept::Q1"]
    assert [child.id for child in nodes["concept::Q1"].children] == ["concept::Q2"]


def test_subtrees_returns_the_highest_node_of_a_type_not_its_descendants() -> None:
    outer = Label(id="category::Law", type="category", value="Law", labels=[])
    inner = _parented("category::Framework", "category", "Framework", [outer])
    nodes = tree(merge([outer, inner], []), ["category"])
    assert [node.id for node in nodes] == ["category::Law"]


def test_subtrees_dedupes_a_node_reachable_from_two_roots() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    shared = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    nodes = tree(merge([law, policy], [_fetched(shared)]), ["concept"])
    assert [node.id for node in nodes] == ["concept::Q1"]


def test_types_spans_the_whole_subtree() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    concept = _parented("concept::Q1", "concept", "Flooding", [law])
    keyword = _parented("keyword::Flood", "keyword", "Flood", [concept])
    roots = tree(merge([law], [_fetched(concept), _fetched(keyword)]), None)
    assert roots[0].types() == {"category", "concept", "keyword"}


def test_set_count_reaches_a_shared_node_once_per_id() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    shared = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    roots = tree(merge([law, policy], [_fetched(shared)]), None)
    for root in roots:
        root.set_count({"concept::Q1": 7})
    assert [root.children[0].count for root in roots] == [7, 7]

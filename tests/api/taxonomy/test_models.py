from pathlib import PurePosixPath

from api.taxonomy.models import LabelNode, merge, select, tree
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
    region = _by_id(tree(merged))["region::SA"]
    assert [child.id for child in region.children] == ["country::BOL"]


def test_a_fetched_child_attaches_to_its_hardcoded_parent() -> None:
    subdivision = _parented(
        "subdivision::BO-X", "subdivision", "Somewhere", [_country(VESPA_NAME)]
    )
    merged = merge([REGION, _country(HARDCODED_NAME)], [_fetched(subdivision)])
    country = _by_id(tree(merged))["region::SA"].children[0]
    assert country.value == HARDCODED_NAME
    assert [child.id for child in country.children] == ["subdivision::BO-X"]


def test_a_label_only_vespa_knows_about_is_kept() -> None:
    keyword = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    merged = merge([REGION], [_fetched(keyword, ["Flooding"])])
    assert "keyword::Flood" in _by_id(tree(merged))


def test_alternative_labels_survive_onto_the_node() -> None:
    keyword = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    merged = merge([REGION], [_fetched(keyword, ["Flooding", "Inundation"])])
    node = _by_id(tree(merged))["keyword::Flood"]
    assert node.alternative_labels == ["Flooding", "Inundation"]


def test_a_hardcoded_label_has_no_alternative_labels() -> None:
    node = _by_id(tree(merge([REGION], [])))["region::SA"]
    assert node.alternative_labels == []


def _concept(id: str, alternative_labels: list[str], parent: str | None = None) -> LabelSearchResult:
    parents = [Label(id=parent, type="concept", value="Flooding")] if parent else []
    return _fetched(
        _parented(id, "concept", "Flooding", parents), alternative_labels
    )


def test_a_parent_seen_first_as_a_relationship_keeps_its_alternative_labels() -> None:
    parent = _concept("concept::Q1", ["inundation", "flood"])
    child = _concept("concept::Q2", ["flash flooding"], parent="concept::Q1")
    nodes = _by_id(tree(merge([], [child, parent])))
    assert nodes["concept::Q1"].alternative_labels == ["inundation", "flood"]


def test_alternative_labels_are_deduped() -> None:
    parent = _concept("concept::Q1", ["inundation", "flood", "inundation"])
    child = _concept("concept::Q2", ["flash flooding"], parent="concept::Q1")
    nodes = _by_id(tree(merge([], [child, parent])))
    assert nodes["concept::Q1"].alternative_labels == ["inundation", "flood"]


def test_a_label_with_two_parents_hangs_under_both() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    both = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    nodes = _by_id(tree(merge([law, policy], [_fetched(both)])))
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
    nodes = _by_id(tree(merge([], [_fetched(orphan)])))
    assert list(nodes) == ["concept::Q1"]
    assert [child.id for child in nodes["concept::Q1"].children] == ["concept::Q2"]


CLIMATE = Label(id="domain::Climate", type="domain", value="Climate", labels=[])


def _climate_tree() -> list[LabelNode]:
    law = _parented("category::Law", "category", "Law", [CLIMATE])
    flood = _parented("keyword::Flood", "keyword", "Flood", [law])
    drought = _parented("keyword::Drought", "keyword", "Drought", [law])
    slashed = _parented(
        "activity_status::Amended/Updated",
        "activity_status",
        "Amended/Updated",
        [CLIMATE],
    )
    fetched = [_fetched(label) for label in (law, flood, drought, slashed)]
    return tree(merge([CLIMATE], fetched))


def _found(pattern: str) -> list[str]:
    return [
        found.ids[-1]
        for root in _climate_tree()
        for found in root.find_path(PurePosixPath(pattern))
    ]


def _found_paths(pattern: str) -> list[tuple[str, ...]]:
    return [
        found.ids
        for root in _climate_tree()
        for found in root.find_path(PurePosixPath(pattern))
    ]


def test_a_match_carries_the_path_it_was_found_at() -> None:
    assert _found_paths("**/keyword::Flood") == [
        ("domain::Climate", "category::Law", "keyword::Flood"),
    ]


def test_a_double_star_finds_a_type_at_any_depth() -> None:
    assert sorted(_found("**/keyword::*")) == ["keyword::Drought", "keyword::Flood"]


def test_a_single_star_pins_the_depth() -> None:
    assert _found("*/keyword::*") == []


def test_an_exact_path_finds_one_node() -> None:
    assert _found("domain::Climate/category::Law/keyword::Flood") == ["keyword::Flood"]


def test_a_wrong_first_segment_finds_nothing() -> None:
    assert _found("domain::Nature/**") == []


def test_a_trailing_double_star_includes_the_node_itself() -> None:
    """
    `x/**` means x and everything under it.

    This departs from `PurePosixPath.full_match`, where a trailing `**` requires
    at least one further segment, so `x/**` does not match `x`.
    """
    assert sorted(_found("domain::Climate/**")) == [
        "activity_status::Amended/Updated",
        "category::Law",
        "domain::Climate",
        "keyword::Drought",
        "keyword::Flood",
    ]


def test_a_double_star_in_the_middle_still_constrains_the_tail() -> None:
    assert sorted(_found("domain::Climate/**/keyword::*")) == [
        "keyword::Drought",
        "keyword::Flood",
    ]


def test_a_leading_double_star_matches_zero_segments() -> None:
    assert _found("**/domain::Climate") == ["domain::Climate"]


def test_an_id_containing_a_slash_is_matched_by_its_type() -> None:
    """
    The pattern is split into segments, the data never is.

    Were a node's ancestry joined into a path string, this label's own slash
    would split it in two and the pattern would silently miss it.
    """
    assert _found("**/activity_status::*") == ["activity_status::Amended/Updated"]


def test_a_double_star_alone_finds_every_node() -> None:
    assert sorted(_found("**")) == [
        "activity_status::Amended/Updated",
        "category::Law",
        "domain::Climate",
        "keyword::Drought",
        "keyword::Flood",
    ]


def test_a_single_star_alone_finds_only_the_root() -> None:
    assert _found("*") == ["domain::Climate"]


def test_two_double_stars_can_find_the_same_node_twice() -> None:
    """Deduping is the caller's job: `select` already keys selections by id."""
    found = _found("**/**")
    assert len(found) > len(set(found))


def test_subtrees_returns_the_highest_node_of_a_type_not_its_descendants() -> None:
    outer = Label(id="category::Law", type="category", value="Law", labels=[])
    inner = _parented("category::Framework", "category", "Framework", [outer])
    nodes = select(tree(merge([outer, inner], [])), ["**/category::*"])
    assert [node.id for node in nodes] == ["category::Law"]


def test_a_pattern_selects_just_that_subtree() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    nodes = select(tree(merge([law, policy], [])), ["**/category::Law"])
    assert [node.id for node in nodes] == ["category::Law"]


def test_two_patterns_select_both() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    flood = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    nodes = select(tree(merge([law, flood], [])), ["**/keyword::*", "**/category::Law"])
    assert sorted(node.id for node in nodes) == ["category::Law", "keyword::Flood"]


def test_a_pattern_matching_nothing_selects_nothing() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    nodes = select(tree(merge([law], [])), ["**/category::Nonexistent"])
    assert nodes == []


def test_a_match_beneath_another_match_is_not_returned_separately() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    flood = _parented("keyword::Flood", "keyword", "Flood", [law])
    nodes = select(tree(merge([law, flood], [])), ["**/category::*", "**/keyword::Flood"])
    assert [node.id for node in nodes] == ["category::Law"]


def test_no_patterns_selects_every_root() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    flood = Label(id="keyword::Flood", type="keyword", value="Flood", labels=[])
    nodes = select(tree(merge([law, flood], [])), None)
    assert sorted(node.id for node in nodes) == ["category::Law", "keyword::Flood"]


def test_a_match_keeps_the_ancestors_that_lead_to_it() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    climate = Label(id="domain::Climate", type="domain", value="Climate", labels=[])
    flood = _parented("category::Flood", "category", "Flood", [law, climate])
    nodes = select(tree(merge([law, climate], [_fetched(flood)])), ["**/category::*"])
    assert sorted(node.id for node in nodes) == ["category::Law", "domain::Climate"]
    climate_node = _by_id(nodes)["domain::Climate"]
    assert [child.id for child in climate_node.children] == ["category::Flood"]


def test_a_node_with_two_parents_is_kept_under_each() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    shared = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    nodes = select(tree(merge([law, policy], [_fetched(shared)])), ["**/concept::*"])
    assert sorted(node.id for node in nodes) == ["category::Law", "category::Policy"]
    for node in nodes:
        assert [child.id for child in node.children] == ["concept::Q1"]


def test_a_match_is_a_leaf_unless_its_children_matched_too() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    flood = _parented("keyword::Flood", "keyword", "Flood", [law])
    roots = tree(merge([law], [_fetched(flood)]))
    assert [node.id for node in select(roots, ["**/category::*"])] == ["category::Law"]
    assert select(roots, ["**/category::*"])[0].children == []
    assert select(roots, ["**/category::*/**"])[0].children[0].id == "keyword::Flood"


def test_types_spans_the_whole_subtree() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    concept = _parented("concept::Q1", "concept", "Flooding", [law])
    keyword = _parented("keyword::Flood", "keyword", "Flood", [concept])
    roots = tree(merge([law], [_fetched(concept), _fetched(keyword)]))
    assert roots[0].types() == {"category", "concept", "keyword"}


def test_counts_reach_a_shared_node_under_every_parent() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    policy = Label(id="category::Policy", type="category", value="Policy", labels=[])
    shared = _parented("concept::Q1", "concept", "Flooding", [law, policy])
    roots = tree(merge([law, policy], [_fetched(shared)]))
    counted = [root.response({"concept::Q1": 7}) for root in roots]
    assert [root.children[0].count for root in counted] == [7, 7]


def test_a_count_is_not_written_onto_the_shared_tree() -> None:
    law = Label(id="category::Law", type="category", value="Law", labels=[])
    roots = tree(merge([law], []))
    first = roots[0].response({"category::Law": 7})
    second = roots[0].response({})
    assert [first.count, second.count] == [7, 0]


def test_a_shared_node_is_kept_only_where_the_pattern_matched() -> None:
    """
    A label with two parents sits at two paths, and only one may match.

    Matching by id alone would keep the node under both parents, dragging in the
    unasked-for parent as a connector.
    """
    asked = Label(id="category::Asked", type="category", value="Asked", labels=[])
    other = Label(id="category::Other", type="category", value="Other", labels=[])
    shared = _parented("entity_type::NDC", "entity_type", "NDC", [asked, other])
    roots = tree(merge([asked, other], [_fetched(shared)]))
    nodes = select(roots, ["category::Asked/**"])
    assert [node.id for node in nodes] == ["category::Asked"]
    assert [child.id for child in nodes[0].children] == ["entity_type::NDC"]

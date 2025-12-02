"""Tests for Label model."""

from hypothesis import given
from hypothesis import strategies as st
from knowledge_graph.identifiers import Identifier

from search.label import Label
from tests.common_strategies import label_data_strategy, label_strategy, text_strategy


@given(label_data=label_data_strategy())
def test_whether_label_id_is_deterministic_for_same_inputs(label_data):
    label1 = Label(**label_data)
    label2 = Label(**label_data)
    assert label1.id == label2.id
    assert isinstance(label1.id, Identifier)


@given(
    label=label_strategy(), labels_list=st.lists(text_strategy, min_size=2, max_size=5)
)
def test_whether_label_ids_are_invariant_to_the_order_of_their_alternative_labels(
    label, labels_list
):
    if len(labels_list) >= 2:
        label_with_ordered = label.model_copy(
            update={"alternative_labels": labels_list}
        )
        label_with_reversed = label.model_copy(
            update={"alternative_labels": list(reversed(labels_list))}
        )
        assert label_with_ordered.id == label_with_reversed.id


@given(
    label=label_strategy(), labels_list=st.lists(text_strategy, min_size=2, max_size=5)
)
def test_whether_label_ids_are_invariant_to_the_order_of_their_negative_labels(
    label, labels_list
):
    if len(labels_list) >= 2:
        label_with_ordered = label.model_copy(update={"negative_labels": labels_list})
        label_with_reversed = label.model_copy(
            update={"negative_labels": list(reversed(labels_list))}
        )
        assert label_with_ordered.id == label_with_reversed.id


@given(label=label_strategy(), new_preferred_label=text_strategy)
def test_whether_label_id_changes_when_preferred_label_changes(
    label, new_preferred_label
):
    if new_preferred_label != label.preferred_label:
        label_with_new_preferred = label.model_copy(
            update={"preferred_label": new_preferred_label}
        )
        assert label.id != label_with_new_preferred.id


@given(label=label_strategy(), new_description=st.one_of(st.none(), text_strategy))
def test_whether_label_id_changes_when_description_changes(label, new_description):
    if new_description != label.description:
        label_with_new_description = label.model_copy(
            update={"description": new_description}
        )
        assert label.id != label_with_new_description.id


@given(
    label=label_strategy(), new_alternative_labels=st.lists(text_strategy, max_size=5)
)
def test_whether_label_id_changes_when_alternative_labels_change(
    label, new_alternative_labels
):
    if sorted(new_alternative_labels) != sorted(label.alternative_labels):
        label_with_new_alternatives = label.model_copy(
            update={"alternative_labels": new_alternative_labels}
        )
        assert label.id != label_with_new_alternatives.id


@given(label=label_strategy(), new_negative_labels=st.lists(text_strategy, max_size=5))
def test_whether_label_id_changes_when_negative_labels_change(
    label, new_negative_labels
):
    if sorted(new_negative_labels) != sorted(label.negative_labels):
        label_with_new_negatives = label.model_copy(
            update={"negative_labels": new_negative_labels}
        )
        assert label.id != label_with_new_negatives.id


@given(label=label_strategy())
def test_whether_labels_can_be_created_with_a_missing_description(label):
    label_with_none_description = label.model_copy(update={"description": None})
    assert isinstance(label_with_none_description.id, Identifier)

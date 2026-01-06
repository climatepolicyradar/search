"""Tests for Label model."""

import pytest
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


@given(label=label_strategy(), new_source=text_strategy)
def test_whether_label_id_changes_when_source_changes(label, new_source):
    if new_source != label.source:
        label_with_new_source = label.model_copy(update={"source": new_source})
        assert label.id != label_with_new_source.id


@given(label=label_strategy(), new_id_at_source=text_strategy)
def test_whether_label_id_changes_when_id_at_source_changes(label, new_id_at_source):
    if new_id_at_source != label.id_at_source:
        label_with_new_id_at_source = label.model_copy(
            update={"id_at_source": new_id_at_source}
        )
        assert label.id != label_with_new_id_at_source.id


@pytest.mark.parametrize(
    "field_name,value_strategy",
    [
        ("preferred_label", text_strategy),
        ("description", st.one_of(st.none(), text_strategy)),
        ("alternative_labels", st.lists(text_strategy, max_size=5)),
        ("negative_labels", st.lists(text_strategy, max_size=5)),
    ],
)
@given(label=label_strategy(), data=st.data())
def test_whether_label_id_is_invariant_to_field_changes(
    label, data, field_name, value_strategy
):
    new_value = data.draw(value_strategy)
    current_value = getattr(label, field_name)

    # For lists, compare sorted values
    if isinstance(current_value, list):
        if sorted(new_value) != sorted(current_value):
            label_with_new_value = label.model_copy(update={field_name: new_value})
            assert label.id == label_with_new_value.id
    else:
        if new_value != current_value:
            label_with_new_value = label.model_copy(update={field_name: new_value})
            assert label.id == label_with_new_value.id


@given(label=label_strategy())
def test_whether_labels_can_be_created_with_a_missing_description(label):
    label_with_none_description = label.model_copy(update={"description": None})
    assert isinstance(label_with_none_description.id, Identifier)

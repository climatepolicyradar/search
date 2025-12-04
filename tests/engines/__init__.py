from search import Primitive
from search.document import Document
from search.label import Label
from search.passage import Passage


def get_valid_search_term(item: Primitive) -> str:
    """Extract a valid searchable term from any primitive type."""
    if isinstance(item, Document):
        string_field = item.title
    elif isinstance(item, Passage):
        string_field = item.text
    elif isinstance(item, Label):
        string_field = item.preferred_label
    else:
        raise ValueError(f"Unknown primitive type: {type(item)}")

    return string_field.split()[0]

"""Hypothesis strategies for generating test data."""

from hypothesis import provisional
from hypothesis import strategies as st
from knowledge_graph.identifiers import Identifier

from search.document import Document
from search.label import Label
from search.passage import Passage

text_strategy = st.text(min_size=1, max_size=400)

url_strategy = provisional.urls()

# document_id follows patterns like "UNFCCC.document.i00002313.n0000" or "CPR.document.i00004577.n0000"
document_id_strategy = st.one_of(
    st.builds(
        lambda source, num: f"{source}.document.i{num:08d}.n0000",
        st.sampled_from(["UNFCCC", "CPR", "CCLW", "GCF", "GEF", "AF", "CIF"]),
        st.integers(min_value=0, max_value=99999999),
    ),
    st.builds(
        lambda source, num: f"{source}.party.{num}.0",
        st.sampled_from(["UNFCCC"]),
        st.integers(min_value=1, max_value=9999),
    ),
    st.builds(
        lambda source, num, num2: f"{source}.executive.{num}.{num2}",
        st.sampled_from(["CCLW"]),
        st.integers(min_value=1, max_value=99999),
        st.integers(min_value=1, max_value=99999),
    ),
    st.builds(
        lambda source, text, num: f"{source}.legislative.{text}.{num}",
        st.sampled_from(["CCLW"]),
        st.text(min_size=1, max_size=10),
        st.integers(min_value=1, max_value=99999),
    ),
)

# text_block.text_block_id is typically a numeric string
text_block_id_strategy = st.integers(min_value=1, max_value=999999).map(str)

# text_block.text can be very short (1-400 chars, avg ~30)
text_block_text_strategy = st.text(min_size=1, max_size=400)

# document_metadata.description often contains HTML like <p>...</p>
document_description_strategy = st.one_of(
    st.builds(lambda text: f"<p>{text}</p>", text_strategy),
    text_strategy,
)


@st.composite
def huggingface_row_strategy(
    draw,
    include_source_url=True,
    include_title=True,
    include_description=True,
    include_document_id=True,
    include_text_block=True,
    include_text_block_id=True,
):
    """
    Generate a dict for testing how documents/passages are created.

    The format of the row matches the structure of the HuggingFace dataset:
    https://huggingface.co/datasets/climatepolicyradar/all-document-text-data
    """
    row = {}

    if include_source_url:
        row["document_metadata.source_url"] = draw(url_strategy)

    if include_title:
        row["document_metadata.document_title"] = draw(text_strategy)

    if include_description:
        row["document_metadata.description"] = draw(document_description_strategy)

    if include_document_id:
        row["document_id"] = draw(document_id_strategy)

    if include_text_block:
        row["text_block.text"] = draw(text_strategy)

    if include_text_block_id:
        row["text_block.text_block_id"] = draw(text_block_id_strategy)

    return row


@st.composite
def label_data_strategy(draw) -> dict:
    """Generate input data for Label model."""
    return {
        "preferred_label": draw(text_strategy),
        "alternative_labels": draw(st.lists(text_strategy, max_size=5)),
        "negative_labels": draw(st.lists(text_strategy, max_size=5)),
        "description": draw(st.one_of(st.none(), text_strategy)),
        "source": draw(text_strategy),
        "id_at_source": draw(text_strategy),
    }


@st.composite
def label_strategy(draw) -> Label:
    """Generate a Label instance for testing."""
    return Label(**draw(label_data_strategy()))


@st.composite
def document_data_strategy(draw) -> dict:
    """Generate input data for Document model."""
    return {
        "title": draw(text_strategy),
        "source_url": draw(url_strategy),
        "description": draw(text_strategy),
        "original_document_id": draw(document_id_strategy),
    }


@st.composite
def document_strategy(draw) -> Document:
    """Generate a Document instance for testing."""
    return Document(**draw(document_data_strategy()))


@st.composite
def passage_data_strategy(draw) -> dict:
    """Generate input data for Passage model."""
    document_id = Identifier.generate(draw(text_strategy), draw(url_strategy))

    return {
        "text": draw(text_strategy),
        "document_id": document_id,
        "original_passage_id": draw(text_block_id_strategy),
        "labels": [],
    }


@st.composite
def passage_strategy(draw) -> Passage:
    """Generate a Passage instance for testing."""
    return Passage(**draw(passage_data_strategy()))


# General search strategies
search_terms_strategy = st.text(min_size=0, max_size=1000)
search_limit_strategy = st.one_of(st.none(), st.integers(min_value=1, max_value=10000))
search_offset_strategy = st.integers(min_value=0, max_value=1000000)

"""Unit tests for the passages feeder's record derivers."""

from passages_flow import derive_heading_text, derive_passage_data


def _record_with_topics() -> dict:
    return {
        "fields": {
            "document_id": {"assign": "doc-0"},
            "topics": {
                "assign": [
                    {
                        "id": "topic-1",
                        "concept_id": "finance flow",
                        "classifier_id": "classifier-1",
                        "end_index": 12,
                        "labelled_text": "finance flow",
                        "labellers": ['BertBasedClassifier("finance flow")'],
                        "prediction_probability": 0.9,
                        "start_index": 0,
                        "timestamps": ["2024-01-01T00:00:00"],
                        "value": "finance flow",
                    }
                ]
            },
        }
    }


def test_derive_passage_data_derives_labels_and_document_ref() -> None:
    """Both derivers apply: topics become labels, and document_ref is set from document_id."""
    record = derive_passage_data(_record_with_topics())

    assert record["fields"]["document_ref"] == {
        "assign": "id:documents:documents::doc-0"
    }
    assert record["fields"]["labels"] == {
        "assign": [
            {
                "id": "concept::finance flow",
                "type": "concept",
                "value": "finance flow",
                "classifier_id": "classifier-1",
                "end_index": 12,
                "labelled_text": "finance flow",
                "labellers": ['BertBasedClassifier("finance flow")'],
                "prediction_probability": 0.9,
                "start_index": 0,
                "timestamps": ["2024-01-01T00:00:00"],
            }
        ]
    }
    assert "topics" not in record["fields"]
    assert record["fields"]["concept_counts"] == {
        "assign": {"concept::finance flow": 1}
    }


def _topic(concept_id: str, start_index: int) -> dict:
    """One topic span, as the data-lake export emits them."""
    return {
        "id": f"topic-{concept_id}-{start_index}",
        "concept_id": concept_id,
        "classifier_id": "classifier-1",
        "end_index": start_index + 4,
        "labelled_text": concept_id,
        "labellers": [f'BertBasedClassifier("{concept_id}")'],
        "prediction_probability": 0.9,
        "start_index": start_index,
        "timestamps": ["2024-01-01T00:00:00"],
        "value": concept_id,
    }


def test_derive_passage_data_counts_repeated_concept_spans() -> None:
    """Each topic is one span, so a concept mentioned twice counts twice."""
    record = derive_passage_data(
        {
            "fields": {
                "document_id": {"assign": "doc-0"},
                "topics": {
                    "assign": [
                        _topic("Q1343", 0),
                        _topic("Q1343", 20),
                        _topic("Q638", 40),
                    ]
                },
            }
        }
    )

    assert record["fields"]["concept_counts"] == {
        "assign": {"concept::Q1343": 2, "concept::Q638": 1}
    }
    # The counts collapse the same ids `labels` repeats, one entry per span.
    assert len(record["fields"]["labels"]["assign"]) == 3


def test_derive_passage_data_emits_empty_concept_counts_without_topics() -> None:
    """A passage with no topics gets an empty tensor, not a missing field."""
    record = derive_passage_data({"fields": {"document_id": {"assign": "doc-0"}}})

    assert record["fields"]["concept_counts"] == {"assign": {}}


def test_derive_passage_data_sets_the_type_flags_from_content_and_pages() -> None:
    """
    The flags land on the record, and the detectors see the record's page numbers.

    Covers the wiring only - the rulesets themselves are tested in
    test_passages_derived_data.py. A contents listing is used because it is the
    one detector that reads `pages`: on page 3 it fires, on page 42 the
    front-matter veto rejects it.
    """
    contents_listing = (
        "1. Acknowledgement 6\n"
        "2. About the Guideline 7\n"
        "2.1. Purpose of the Guideline 7\n"
        "2.2. Scope of the Guideline 8\n"
        "2.2.1. Applicability 8\n"
        "2.2.2. Exemption 9\n"
        "2.2.3. Precedence 9\n"
        "2.2.4. Reference Standards and green building rating programmes 10"
    )

    def flags(page_number: int) -> dict:
        record = derive_passage_data(
            {
                "fields": {
                    "document_id": {"assign": "doc-0"},
                    "content": {"assign": contents_listing},
                    "pages": {"assign": [{"number": page_number}]},
                }
            }
        )
        return {
            name: record["fields"][name]
            for name in (
                "looks_like_short_heading",
                "looks_like_table_of_contents",
                "looks_like_reference_list",
            )
        }

    assert flags(3) == {
        "looks_like_short_heading": {"assign": False},
        "looks_like_table_of_contents": {"assign": True},
        "looks_like_reference_list": {"assign": False},
    }
    assert flags(42)["looks_like_table_of_contents"] == {"assign": False}


def test_derive_passage_data_handles_a_record_with_no_pages() -> None:
    """Passages from HTML documents have no page data - the export omits `pages`."""
    record = derive_passage_data(
        {"fields": {"document_id": {"assign": "doc-0"}, "content": {"assign": "Hello"}}}
    )

    assert record["fields"]["looks_like_table_of_contents"] == {"assign": False}


def _record(serialised_text: str | None, content: str = "") -> dict:
    """One export record, carrying only the fields `derive_heading_text` reads."""
    fields: dict = {
        "document_id": {"assign": "doc-0"},
        "content": {"assign": content},
    }
    if serialised_text is not None:
        fields["serialised_text"] = {"assign": serialised_text}
    return {"fields": fields}


def _serialised(heading: str, content: str) -> str:
    """
    `serialised_text` exactly as the data-lake export builds it.

    The prefix is spelled out here rather than imported from `passages_flow`, so a
    typo in the constant fails these tests rather than passing them.
    """
    return (
        "Section context: this excerpt is from the section titled "
        f"'{heading}'. {content}"
    )


def test_derive_heading_text_parses_the_section_context_prefix() -> None:
    """
    The heading is lifted out of `serialised_text`, the only place it arrives.

    The export has no `heading_text` column - only `heading_id`, which points at
    another passage this per-record deriver cannot see.
    """
    content = (
        "Victor Manuel Garcia Lemus Chapter 10 or Master of Science in Public Health"
    )
    record = derive_heading_text(
        _record(_serialised("Appendix 2: Authors", content), content)
    )

    assert record["fields"]["heading_text"] == {"assign": "Appendix 2: Authors"}


def test_derive_heading_text_keeps_apostrophes_in_the_heading() -> None:
    """
    Real headings contain apostrophes, so the parse must not stop at the first one.

    "Authors' comments on the State party's observations on admissibility" is a real
    corpus heading, and one the demoted-section detector must NOT fire on - so
    truncating it here would silently change that verdict too.
    """
    heading = "Authors' comments on the State party's observations on admissibility"
    content = (
        "The authors submit that the State party has failed to address the merits."
    )
    record = derive_heading_text(_record(_serialised(heading, content), content))

    assert record["fields"]["heading_text"] == {"assign": heading}


def test_derive_heading_text_trims_content_rather_than_matching_a_delimiter() -> None:
    """
    The split point comes from `content`'s length, not from searching for `'. `.

    Synthetic heading: a misparsed heading can carry a quoted phrase closing with the
    same `'. ` the prefix uses. Searching for the first occurrence truncates here;
    trimming `content` off the end cannot.
    """
    heading = "Definition of 'reference year'. References"
    content = (
        "Reference year means the base year against which reductions are measured."
    )
    record = derive_heading_text(_record(_serialised(heading, content), content))

    assert record["fields"]["heading_text"] == {"assign": heading}


def test_derive_heading_text_handles_content_that_repeats_the_heading() -> None:
    """
    A section whose first passage restates its own heading still parses.

    Guards the `endswith(content)` trim: the word "References" appears both as the
    heading and at the start of `content`, and only the trailing copy may be removed.
    """
    content = "References to Chapter 7 and 8 are set out below."
    record = derive_heading_text(_record(_serialised("References", content), content))

    assert record["fields"]["heading_text"] == {"assign": "References"}


def test_derive_heading_text_is_absent_without_the_prefix() -> None:
    """
    Passages with no `heading_id` carry no prefix to parse.

    The field is left alone rather than assigned `""`.
    """
    record = derive_heading_text(_record("Some other serialisation of the passage."))

    assert "heading_text" not in record["fields"]


def test_derive_heading_text_handles_a_missing_serialised_text() -> None:
    """The deriver must not raise if the export omits the field entirely."""
    record = derive_heading_text(_record(None, content="Hello"))

    assert "heading_text" not in record["fields"]


def test_derive_heading_text_ignores_an_empty_heading() -> None:
    """An empty quoted title yields no field, rather than an empty-string assign."""
    content = "Some body text."
    record = derive_heading_text(_record(_serialised("", content), content))

    assert "heading_text" not in record["fields"]


def test_derive_passage_data_sets_heading_text() -> None:
    """
    `heading_text` lands via the full deriver chain, not just the deriver alone.

    Values are taken verbatim from `ICCN.document.i00000042.n0000`, so this doubles
    as a regression anchor against the real export format.
    """
    content = "https://doi.org/10.1186/s13071-016-1403-y Other development indicators"
    record = derive_passage_data(
        _record(_serialised("10.8 BIBLIOGRAPHIC REFERENCES", content), content)
    )

    assert record["fields"]["heading_text"] == {
        "assign": "10.8 BIBLIOGRAPHIC REFERENCES"
    }


def test_derive_heading_text_skips_a_partial_update_without_content() -> None:
    """
    Without `content` there is nothing to trim, so nothing is written.

    Partial updates may carry `serialised_text` alone. Parsing regardless would
    assign the whole passage body as the heading, and `heading_text` is indexed.
    """
    record = derive_heading_text(
        {
            "fields": {
                "document_id": {"assign": "doc-0"},
                "serialised_text": {"assign": _serialised("Appendix 2", "Some body.")},
            }
        }
    )

    assert "heading_text" not in record["fields"]


def test_derive_heading_text_skips_content_that_is_not_the_exact_tail() -> None:
    """A whitespace mismatch between the two copies of the body is not guessed at."""
    content = "Some body text."
    record = derive_heading_text(
        _record(_serialised("Appendix 2", content), content + "\n")
    )

    assert "heading_text" not in record["fields"]

"""Vespa `<hi>` bolding, as tag-free text plus the spans the tags marked."""

from pydantic import BaseModel

from search.span import BaseSpan

_HI_OPEN = "<hi>"
_HI_CLOSE = "</hi>"


class Bolding(BaseSpan[None]):
    """
    A span of a passage's text that Vespa matched against the query.

    @see: https://docs.vespa.ai/en/reference/schemas/schemas.html#bolding
    """

    # There is nothing to wrap the matched text in as it is just freetext.
    value: None = None


class BoldedText(BaseModel):
    """Text stripped of Vespa's `<hi>` tags, with the spans they marked."""

    text: str  # the text stripped of <hi> tags
    boldings: list[Bolding]


def bolding_to_labels(bolded_text: str) -> BoldedText:
    """
    Convert Vespa's `<hi>` tags to the stripped text plus a list of Boldings.

    Indices relate the text with the tags stripped out as this is the text
    the client is sent - so `labelled_text == text[start_index:end_index]`.
    """
    boldings: list[Bolding] = []
    current_index = 0
    tag_characters_removed = 0
    while True:
        start_tag_index = bolded_text.find(_HI_OPEN, current_index)
        if start_tag_index == -1:
            break
        end_tag_index = bolded_text.find(_HI_CLOSE, start_tag_index)
        if end_tag_index == -1:
            break
        labelled_text = bolded_text[start_tag_index + len(_HI_OPEN) : end_tag_index]
        start_index = start_tag_index - tag_characters_removed
        boldings.append(
            Bolding(
                start_index=start_index,
                end_index=start_index + len(labelled_text),
                labelled_text=labelled_text,
            )
        )
        tag_characters_removed += len(_HI_OPEN) + len(_HI_CLOSE)
        current_index = end_tag_index + len(_HI_CLOSE)

    return BoldedText(
        text=bolded_text.replace(_HI_OPEN, "").replace(_HI_CLOSE, ""),
        boldings=boldings,
    )


def merge_bolded(*bolded_texts: str) -> BoldedText:
    """
    Merge several bolded copies of the same text into one set of Boldings.

    A quoted query is bolded on two fields with the same source text: the
    stemmed field bolds the free text, the `*_not_stemmed` one the phrases.
    Overlapping or touching spans are joined into one.

    :raises ValueError: if the copies are not the same text once untagged, as
        their spans would then not line up.
    """
    parsed = [bolding_to_labels(t) for t in bolded_texts]
    text = parsed[0].text
    if any(p.text != text for p in parsed[1:]):
        raise ValueError("Bolded copies of a field do not share the same text")

    spans = sorted((b.start_index, b.end_index) for p in parsed for b in p.boldings)
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return BoldedText(
        text=text,
        boldings=[
            Bolding(start_index=start, end_index=end, labelled_text=text[start:end])
            for start, end in merged
        ],
    )


def render_bolded(bolded: BoldedText) -> str:
    """Put Vespa's `<hi>` tags back around each Bolding."""
    out: list[str] = []
    previous_end = 0
    for b in bolded.boldings:
        out.append(bolded.text[previous_end : b.start_index])
        out.append(f"{_HI_OPEN}{b.labelled_text}{_HI_CLOSE}")
        previous_end = b.end_index
    out.append(bolded.text[previous_end:])
    return "".join(out)

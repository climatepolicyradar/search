"""Corpus -> provider mapping for relevance tests."""

from typing import Literal

from search.engines.dev_vespa import FieldFilter, Filter

Corpus = Literal["cpr", "cclw", "ccc", "mcf"]


CORPUS_PROVIDERS: dict[Corpus, list[str]] = {
    "cpr": [
        "Adaptation Fund",
        "Climate Policy Radar",
        # Being discussed with programmes
        "CPR.corpus.i00000589.n0000",
        "Global Environment Facility",
        "Gold Standard",
        "Grantham Research Institute",
        "Green Climate Fund",
        "Laws Africa",
        "NewClimate Institute",
        "Ocean Energy Pathways",
        "The Climate Investment Funds",
        "UNCBD",
        "UNCCD",
        "UNDRR",
        "UNFCCC",
    ],
    "cclw": [
        "Gold Standard",
        "Grantham Research Institute",
        "Laws Africa",
        "NewClimate Institute",
        "UNDRR",
        "UNFCCC",
    ],
    "ccc": [
        "Sabin Center for Climate Change Law",
    ],
    "mcf": [
        "Adaptation Fund",
        "Global Environment Facility",
        "Green Climate Fund",
        "The Climate Investment Funds",
    ],
}


def build_corpus_filter(corpus: Corpus) -> Filter:
    """
    Build a Vespa filter restricting results to documents in `corpus`.

    Provider labels are stored with `id = "agent::" + value`.
    """
    providers = CORPUS_PROVIDERS[corpus]
    return Filter(
        op="or",
        filters=[
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value=f"agent::{provider}",
            )
            for provider in providers
        ],
    )

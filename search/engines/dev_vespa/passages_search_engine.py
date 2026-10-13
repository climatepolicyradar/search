"""The passage search engine for dev Vespa."""

from __future__ import annotations

from typing import Any

from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa.labels import DevVespaInstanceAddIn
from search.engines.vespa_query.client import (
    Settings,
    _get_total_count,
    execute_vespa_query,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    Filter,
    _build_filter_query,
    _topic_ids_from_filters,
)
from search.engines.vespa_query.query_text_modifiers import (
    _normalize_currency_symbols,
    _parse_query,
)
from search.engines.vespa_query.sorting import _ranking_overrides_for_passage_order_by
from search.log import get_logger
from search.passage import Passage
from search.vespa.passage import VespaPassage

logger = get_logger(__name__)

passages_filter_field_to_vespa_field_map: dict[str, list[str]] = {
    "document_id": ["document_id"],
    "principal_id": ["principal_id"],
}
passages_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {
    "labels.value.id": ArrayStructField("labels", "id"),
    "labels.value.value": ArrayStructField("labels", "value"),
    "labels.value.type": ArrayStructField("labels", "type"),
}


_DEFAULT_TOPIC_WEIGHT = 1.0
_DEFAULT_PASSAGE_RANK_PROFILE = "bm25_multiplicative"


# RESEARCH (stemming demo): each stemmer arm's field and rank profile.
# `defaultIndex` must name the field, not a fieldset: through a fieldset, Vespa
# stems the query with the default English (Porter) stemmer, so "informal" also
# searched "inform" on the kstem/minimal fields.
_STEM_VARIANTS: dict[str, tuple[str, str]] = {
    "porter": ("content", "bm25_multiplicative"),
    "kstem": ("content_kstem", "bm25_multiplicative_kstem"),
    "minimal": ("content_minimal", "bm25_multiplicative_minimal"),
}


def _passage_phrase_yql(count: int) -> str:
    """One in-order phrase clause per quoted phrase."""
    return "".join(
        " and content_not_stemmed contains "
        f"({{grammar.composite:'phrase'}}text(@exact_phrase_{i}))"
        for i in range(count)
    )


def _passage_summary(*, debug: bool, bolding: bool, has_phrases: bool) -> str:
    """
    The summary class to request.

    `search-exact` adds `content_not_stemmed`, which is where quoted phrases match
    and so the only place they get bolded. It costs a second copy of the text per
    hit, so it is only requested when there is a phrase to bold.
    """
    if debug:
        return "debug-summary"
    if bolding and has_phrases:
        return "search-exact"
    return "search"


class DevVespaPassageSearchEngine(DevVespaInstanceAddIn, SearchEngine[Passage]):
    """Search engine for passages in dev Vespa."""

    model_class = Passage

    def __init__(
        self,
        settings: Settings,
        debug: bool = False,
        ranking_profile: str = _DEFAULT_PASSAGE_RANK_PROFILE,
        topic_weight: float = _DEFAULT_TOPIC_WEIGHT,
        exact_weight: float | None = None,
        stem_variant: str | None = None,
    ) -> None:
        """Initialise the search engine."""
        if stem_variant is not None and stem_variant not in _STEM_VARIANTS:
            raise ValueError(
                f"stem_variant must be one of {sorted(_STEM_VARIANTS)}, got {stem_variant!r}"
            )
        if exact_weight is not None and exact_weight < 0:
            raise ValueError(f"exact_weight must be >= 0, got {exact_weight!r}")
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings
        self.ranking_profile = (
            _STEM_VARIANTS[stem_variant][1] if stem_variant else ranking_profile
        )
        self.topic_weight = topic_weight
        self.exact_weight = exact_weight
        self.stem_variant = stem_variant

    @property
    def parameters(self) -> dict[str, Any]:
        """Tuning parameters, surfaced in relevance-test logging."""
        parameters: dict[str, Any] = {
            "ranking_profile": self.ranking_profile,
            "topic_weight": self.topic_weight,
        }
        # Only when set, so the default engine's id (derived from these) is unchanged.
        if self.exact_weight is not None:
            parameters["exact_weight"] = self.exact_weight
        if self.stem_variant is not None:
            parameters["stem_variant"] = self.stem_variant
        return parameters

    def _free_text_yql(self) -> str:
        """
        The free-text half of the YQL.

        For stemming research: with `exact_weight` it is wrapped in `rank()` and
        the query is matched against the unstemmed `exact` fieldset for scoring only, so
        a literal e.g. "informal" outscores a passage that only shares its stem
        e.g. "information". Which passages match is unchanged.
        """
        if self.stem_variant is None:
            match = "userQuery()"
        else:
            fieldset = _STEM_VARIANTS[self.stem_variant][0]
            match = f'({{defaultIndex: "{fieldset}"}}userInput(@query))'
        if self.exact_weight is None:
            return f" and {match}"
        return (
            f" and rank({match}, "
            '({defaultIndex: "exact", grammar: "any"}userInput(@query)))'
        )

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters_json_string: str | None = None,
        bolding: bool = False,
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        free_text, phrases = _parse_query(query) if query else ("", [])

        where = "true"
        filters: Filter | None = None

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(
                filters,
                field_map=passages_filter_field_to_vespa_field_map,
                struct_map=passages_filter_struct_field_to_vespa_field_map,
            )

        yql = f"select * from sources passages where {where}"
        if free_text:
            yql += self._free_text_yql()
        yql += _passage_phrase_yql(len(phrases))

        logger.info(
            "🔎 Passage search query built (query=%r, free_text=%r, phrases=%r, yql=%s)",
            query,
            free_text,
            phrases,
            yql,
        )

        sort_overrides = _ranking_overrides_for_passage_order_by(order_by)

        request_body: dict[str, Any] = {
            "yql": yql,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "rules.rulebase": "passages",
            "presentation.summary": _passage_summary(
                debug=self.debug, bolding=bolding, has_phrases=bool(phrases)
            ),
            "ranking.profile": self.ranking_profile,
        }
        request_body.update(sort_overrides)

        if free_text and self.exact_weight is not None and not sort_overrides:
            request_body["input.query(exact_weight)"] = self.exact_weight
        if self.stem_variant is not None:
            request_body["rules.off"] = True

        if free_text:
            request_body["query"] = _normalize_currency_symbols(free_text)
        for i, phrase in enumerate(phrases):
            request_body[f"exact_phrase_{i}"] = _normalize_currency_symbols(phrase)

        topic_ids = _topic_ids_from_filters(filters)
        if topic_ids and not sort_overrides:
            request_body["input.query(topic_q)"] = dict.fromkeys(topic_ids, 1.0)
            request_body["input.query(topic_weight)"] = self.topic_weight

        # `passage.content` is `bolding: on` in the schema, so Vespa bolds by default -
        # it has to be turned off explicitly.
        if not bolding:
            request_body["presentation.bolding"] = "false"

        response = execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="passages.search",
        )
        passages: list[Passage] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            vespa_passage = VespaPassage.model_validate(fields)
            passages.append(Passage.from_vespa_passage(vespa_passage, bolding=bolding))
            if self.debug:
                debug_info.append(
                    {
                        "relevance": hit.get("relevance"),
                        "summaryfeatures": fields.get("summaryfeatures"),
                        "text_tokens": fields.get("text_tokens"),
                    }
                )

        self.last_debug_info = debug_info

        total_size = _get_total_count(response)
        return ListResponse(
            results=passages, total_size=total_size, next_page_token=None
        )

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()

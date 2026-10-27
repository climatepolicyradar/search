"""The passage search engine for dev Vespa."""

from __future__ import annotations

import json
from typing import Any

from search.acronyms import expansion_patterns
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
    _build_filter_yql,
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


# `content`'s profile, named on the query. Vespa only applies a field's
# profile to query terms when the query names the field; through a fieldset it stems
# with its fallback English stemmer instead.
_QUERY_LINGUISTICS_PROFILE = "passage_analysis_kstem"
# How much an exact match on the unstemmed query is weighted/boosted - see `_free_text_match`. See PR #651 for how this was chosen.
_DEFAULT_EXACT_WEIGHT = 0.1


_SCOPE_YQL = "(document_id in (@document_ids) or principal_id in (@document_ids))"


def _msm_request_fields(msm: float, free_text: str) -> dict[str, float]:
    if msm <= 0.0 or not free_text:
        return {}
    return {"input.query(msm)": msm}


def _passage_phrase_clauses(count: int) -> list[str]:
    """One in-order phrase clause per quoted phrase."""
    return [
        "content_not_stemmed contains "
        f"({{grammar.composite:'phrase'}}text(@exact_phrase_{i}))"
        for i in range(count)
    ]


def _and(clauses: list[str]) -> str | None:
    if not clauses:
        return None
    joined = " and ".join(clauses)
    return f"({joined})" if len(clauses) > 1 else joined


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
        exact_weight: float | None = _DEFAULT_EXACT_WEIGHT,
    ) -> None:
        """
        Initialise the search engine.

        :param exact_weight: How much an exact (unstemmed) match of an unquoted
            search term is weighted/boosted.
        :raises ValueError: if ``exact_weight`` is negative.
        """
        if exact_weight is not None and exact_weight < 0:
            raise ValueError(f"exact_weight must be >= 0, got {exact_weight!r}")
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings
        self.ranking_profile = ranking_profile
        self.topic_weight = topic_weight
        self.exact_weight = exact_weight

    @property
    def parameters(self) -> dict[str, Any]:
        """Tuning parameters, surfaced in relevance-test logging."""
        return {
            "ranking_profile": self.ranking_profile,
            "topic_weight": self.topic_weight,
            "exact_weight": self.exact_weight,
        }

    def _free_text_match(self) -> str:
        """
        The free-text half of the YQL.

        `grammar.profile` stems the query with `content`'s own analyzer, which a
        fieldset query otherwise would not. With `exact_weight`, the match is wrapped
        in `rank()`: the second operand matches the unstemmed `exact` fieldset for
        scoring only, so which passages match is unchanged.
        """
        match = f'({{grammar.profile: "{_QUERY_LINGUISTICS_PROFILE}"}}userInput(@query))'
        if self.exact_weight is None:
            return match
        return (
            f"rank({match}, "
            '({defaultIndex: "exact", grammar: "any"}userInput(@query)))'
        )

    def _where_yql(
        self,
        free_text: str,
        phrases: list[str],
        filters: Filter | None,
    ) -> str:
        filter_query = (
            ""
            if filters is None
            else _build_filter_query(
                filter_group=filters,
                field_map=passages_filter_field_to_vespa_field_map,
                struct_map=passages_filter_struct_field_to_vespa_field_map,
            )
        )
        text_query = "".join(
            f" and {clause}" for clause in self._text_clauses(free_text, phrases)
        )
        return f"true{filter_query}{text_query}"

    def _scoped_where_yql(
        self,
        free_text: str,
        phrases: list[str],
        filters: Filter | None,
    ) -> str:
        filter_yql = (
            None
            if filters is None
            else _build_filter_yql(
                filter_group=filters,
                field_map=passages_filter_field_to_vespa_field_map,
                struct_map=passages_filter_struct_field_to_vespa_field_map,
            )
        )
        text_yql = _and(self._text_clauses(free_text, phrases))
        matched = (
            [f'({text_yql} or labeled({filter_yql}, "filters", 1.0))']
            if filter_yql is not None and text_yql is not None
            else [yql for yql in (text_yql, filter_yql) if yql]
        )
        return " and ".join(["true", _SCOPE_YQL, *matched])

    def _text_clauses(self, free_text: str, phrases: list[str]) -> list[str]:
        free_text_clauses = [self._free_text_match()] if free_text else []
        return [*free_text_clauses, *_passage_phrase_clauses(len(phrases))]

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters: Filter | None = None,
        bolding: bool = False,
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        free_text, phrases = _parse_query(query) if query else ("", [])
        where = self._where_yql(free_text, phrases, filters)
        yql = f"select * from sources passages where {where}"

        logger.info(
            "🔎 Passage search query built (query=%r, free_text=%r, phrases=%r, yql=%s)",
            query,
            free_text,
            phrases,
            yql,
        )

        request_body = self._request_body(
            yql=yql,
            free_text=free_text,
            phrases=phrases,
            filters=filters,
            pagination=pagination,
            order_by=order_by,
            bolding=bolding,
        )

        return self._execute(
            request_body=request_body,
            free_text=free_text,
            bolding=bolding,
            request_context="passages.search",
        )

    def search_within(
        self,
        document_ids: list[str],
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters: Filter | None = None,
        msm: float = 0.0,
        bolding: bool = False,
    ) -> ListResponse[Passage]:
        """
        Find passages within a set of parent documents.

        This differs from `search` in that it ORs filters and the search query and supports MSM.
        This is because a _document_ with e.g. "climate change" and topic:cop does not imply
        the presence of a _passage_ with both set, hence wanting OR based searches for passages.
        """

        free_text, phrases = _parse_query(query) if query else ("", [])
        where = self._scoped_where_yql(free_text, phrases, filters)
        yql = f"select * from sources passages where {where}"

        logger.info(
            "🔎 Scoped passage search query built "
            "(document_ids=%r, query=%r, msm=%s, yql=%s)",
            document_ids,
            query,
            msm,
            yql,
        )

        request_body = self._request_body(
            yql=yql,
            free_text=free_text,
            phrases=phrases,
            filters=filters,
            pagination=pagination,
            order_by=order_by,
            bolding=bolding,
        )

        request_body["document_ids"] = ",".join(json.dumps(i) for i in document_ids)
        request_body.update(_msm_request_fields(msm, free_text))

        return self._execute(
            request_context="passages.search_within",
            request_body=request_body,
            free_text=free_text,
            bolding=bolding,
        )

    def _request_body(
        self,
        yql: str,
        free_text: str,
        phrases: list[str],
        filters: Filter | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        bolding: bool,
    ) -> dict[str, Any]:
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
        return request_body

    def _execute(
        self,
        request_body: dict[str, Any],
        free_text: str,
        bolding: bool,
        request_context: str,
    ) -> ListResponse[Passage]:
        response = execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context=request_context,
        )
        passages: list[Passage] = []
        debug_info: list[dict[str, Any]] = []

        # Vespa matches acronym expansions but cannot bold them - see search/acronyms.py.
        acronym_expansions = expansion_patterns(free_text) if bolding and free_text else []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            vespa_passage = VespaPassage.model_validate(fields)
            passages.append(
                Passage.from_vespa_passage(
                    vespa_passage, bolding=bolding, acronym_expansions=acronym_expansions
                )
            )
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

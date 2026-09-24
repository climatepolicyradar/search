"""The document search engine for dev Vespa."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from typing import Any

import requests
from pydantic import TypeAdapter
from vespa.querybuilder import Grouping as G

from search.data_in_models import Document, DocumentRelationship
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine, VespaError
from search.engines.dev_vespa.labels import (
    MISSING_PLACEHOLDER,
    CountAggregation,
    DevVespaInstanceAddIn,
    get_labels_from_vespa_response,
)
from search.engines.vespa_query.client import (
    API_TIMEOUT,
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    _execute_vespa_query,
    _get_total_count,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    FieldFilter,
    Filter,
    _build_filter_query,
    _facet_filter_label_type,
    _get_label_types_from_filters,
    _prune_filter,
    _topic_ids_from_filters,
)
from search.engines.vespa_query.query_text_modifiers import (
    _normalize_currency_symbols,
    _resolve_geography_aliases,
    _strip_quotes,
)
from search.engines.vespa_query.sorting import _ranking_overrides_for_document_order_by
from search.label import Label
from search.log import get_logger

logger = get_logger(__name__)

documents_filter_field_to_vespa_field_map = {
    "labels.value.id": ["labels.id", "concepts.id"],
    "labels.value.value": ["labels.value", "concepts.value"],
    "labels.type": ["labels.relationship"],
}
documents_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {}

_DEFAULT_TOPIC_WEIGHT = 1.0

# None leaves the rank profile's own default in place.
_DEFAULT_PASSAGES_BREADTH_WEIGHT: float | None = None

# How many candidates weakAnd keeps before the rank profile runs. weakAnd picks them
# with an idf over the `default` fieldset - which includes `passages_text` – so long
# PDFs with many passage hits can crowd out a short exact title match and that document
# is then never scored at all.
# Vespa's own default is max(hits, 100), which ties retrieval depth to the page
# size - so a page_size=500 search matched 5872 documents where the facet query
# for the same terms, running at hits=0, matched 1801. Results and facet counts
# were describing different candidate sets, and `total_count` moved with the
# requested page size. Pinning it here decouples the two. See FUS-475.
_DEFAULT_DOCUMENT_TOTAL_TARGET_HITS = 2000

_DEFAULT_DOCUMENT_RANK_PROFILE = "bm25-title-geo"

# Vespa has no `minimum_should_match`, so MSM lives in the rank profile: turning
# it on means switching profile, not just setting an input.
_DEFAULT_MSM = 0.0
_MSM_DOCUMENT_RANK_PROFILE = "bm25-title-geo-msm"
# A date sort switches to `unranked`, which carries no guard.
_MSM_DOCUMENT_SORT_RANK_PROFILE = "unranked-msm"

# Vespa ignores an input a profile does not declare, so `msm` sent anywhere else
# is a silent no-op. See docs/errors.md.
_MSM_CAPABLE_RANK_PROFILES = frozenset(
    {_MSM_DOCUMENT_RANK_PROFILE, _MSM_DOCUMENT_SORT_RANK_PROFILE}
)


def _resolve_document_rank_profile(ranking_profile: str | None, msm: float) -> str:
    """
    Pick the rank profile for a document search.

    An explicit ``ranking_profile`` wins, so relevance sweeps can pin one.
    Otherwise MSM decides, as it needs a profile declaring ``query(msm)``.

    :param ranking_profile: Caller's explicit choice, or ``None`` to derive one
    :param msm: Fraction of query terms a document must cover, 0.0 - 1.0
    :return: The Vespa rank profile name
    :raises ValueError: if ``msm`` is out of range, or set above 0 on a profile
        that would silently ignore it
    """
    if not 0.0 <= msm <= 1.0:
        raise ValueError(f"msm must be between 0.0 and 1.0, got {msm!r}")

    if ranking_profile is None:
        return (
            _MSM_DOCUMENT_RANK_PROFILE if msm > 0.0 else _DEFAULT_DOCUMENT_RANK_PROFILE
        )

    if msm > 0.0 and ranking_profile not in _MSM_CAPABLE_RANK_PROFILES:
        raise ValueError(
            f"msm={msm} needs a rank profile declaring query(msm); "
            f"{ranking_profile!r} does not. "
            f"Use one of: {sorted(_MSM_CAPABLE_RANK_PROFILES)}"
        )

    return ranking_profile


class DevVespaDocumentSearchEngine(DevVespaInstanceAddIn, SearchEngine[Document]):
    """
    Search engine for dev Vespa

    This class should be using the Vespa Client, but we are having problems connecting to the remote server
    because of the way API Gateway handles trailing slashes.

    i.e.
    VespaClient connects to `/search/`.
    This isn't a viable URL for API Gatewayway, you can use
    - `/search`
    - `/search/{proxy+}`

    The secondary URL uses a `+` which matches 1 or more characters. 🤷

    For now we just use `requests` which yields the same results.
    """

    model_class = Document

    def __init__(
        self,
        settings: Settings,
        debug: bool = False,
        bolding: bool = False,
        ranking_profile: str | None = None,
        topic_weight: float = _DEFAULT_TOPIC_WEIGHT,
        passages_breadth_weight: float | None = _DEFAULT_PASSAGES_BREADTH_WEIGHT,
        total_target_hits: int = _DEFAULT_DOCUMENT_TOTAL_TARGET_HITS,
        msm: float = _DEFAULT_MSM,
    ) -> None:
        """
        Initialise the search engine.

        :param debug: When ``True``, request the ``debug-summary`` document
            summary from Vespa and store per-hit token information in
            :attr:`last_debug_info`.
        :param bolding: When ``True``, matched terms in ``title`` and
            ``description`` are wrapped in ``<hi>`` tags. Search hits never
            carry passages; ``/search/passages`` is the route for those.
        :param ranking_profile: Vespa rank profile to score with. ``None``
            derives one from ``msm`` - ``bm25-title-geo`` when MSM is off,
            ``bm25-title-geo-msm`` when it is on.
        :param topic_weight: How much a filtered-for topic's mention counts
            contribute to relevance. ``0.0`` switches topic ranking off.
        :param passages_breadth_weight: How much the number of matching passages
            contributes to relevance. ``None`` leaves the profile's own default
            (0.1); ``0.0`` switches passage-breadth ranking off. Ignored by
            profiles that do not declare the input.
        :param total_target_hits: How many candidates weakAnd keeps before
            ranking, across the whole content cluster.
            Raising it stops a strong title match being pruned before the rank
            profile ever sees it, at the cost of matching more broadly. See
            :data:`_DEFAULT_DOCUMENT_TOTAL_TARGET_HITS`.
        :param msm: Minimum Should Match - the fraction of the query's terms a
            document must cover to be returned, 0.0 - 1.0. ``0.0`` is off.
            Coverage is the best-matching single passage or the title,
            whichever is higher, so ``1.0`` means "one passage contains the
            whole query", not "these words are somewhere in this 200-page PDF".
        :raises ValueError: if ``msm`` is outside 0.0 - 1.0, or set above 0
            alongside a ``ranking_profile`` that would ignore it.
        """
        self.debug = debug
        self.bolding = bolding
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings
        self.msm = msm
        self.ranking_profile = _resolve_document_rank_profile(ranking_profile, msm)
        self.topic_weight = topic_weight
        self.passages_breadth_weight = passages_breadth_weight
        self.total_target_hits = total_target_hits

    @property
    def _msm_request_fields(self) -> dict[str, float]:
        """
        The ``query(msm)`` input, for every query that must see the same document set.

        Empty when MSM is off, so the request body is unchanged from before this
        parameter existed. Searches, aggregations and facets all carry it: they
        are separate Vespa queries, and a facet counted over a wider set than the
        results is the inconsistency FUS-475 was about.
        """
        if self.ranking_profile not in _MSM_CAPABLE_RANK_PROFILES:
            return {}
        return {"input.query(msm)": self.msm}

    @property
    def parameters(self) -> dict[str, Any]:
        """Tuning parameters, surfaced in the search engine's ID and W&B logging."""
        return {
            "ranking_profile": self.ranking_profile,
            "topic_weight": self.topic_weight,
            "passages_breadth_weight": self.passages_breadth_weight,
            "total_target_hits": self.total_target_hits,
            "msm": self.msm,
        }

    @property
    def _userQuery(self) -> str:
        """
        The text-matching half of the YQL, carrying the weakAnd retrieval depth.

        `userInput(@query)` rather than `userQuery()` because `totalTargetHits`
        only binds to the former. Both build a weakAnd over the `default` fieldset
        and are otherwise equivalent here.
        """
        return (
            f" and (({{totalTargetHits:{self.total_target_hits}}}userInput(@query)) "
            # As geographies and title_synonyms use different Lucene analyzers
            # to the default fieldset, they're referenced explicitly in the query
            # so they can be searched.
            # https://docs.vespa.ai/en/reference/querying/yql.html#defaultindex
            # `geo_query` is `query` with geography aliases resolved to the canonical
            # names carried by the field - see _resolve_geography_aliases.
            ' or ({defaultIndex: "geographies"}userInput(@geo_query))'
            ' or ({defaultIndex: "identifiers"}userInput(@query)))'
        )

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters_json_string: str | None = None,
    ) -> ListResponse[Document]:
        """Fetch a list of relevant search results."""

        if query:
            query = _strip_quotes(query)

        where = "true "
        filters: Filter | None = None

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(
                filters,
                field_map=documents_filter_field_to_vespa_field_map,
                struct_map=documents_filter_struct_field_to_vespa_field_map,
            )

        yql = f"select * from sources documents where {where}"
        if query:
            yql += self._userQuery
        logger.info("🔎 Document search query built (query=%r, yql=%s)", query, yql)

        sort_overrides = _ranking_overrides_for_document_order_by(order_by)
        if sort_overrides and self.msm > 0.0:
            # MSM changes which documents exist, not just their order, so a
            # sort cannot opt out of it the way the weights below do.
            sort_overrides["ranking.profile"] = _MSM_DOCUMENT_SORT_RANK_PROFILE

        normalized_query = _normalize_currency_symbols(query) if query else query

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": normalized_query,
            "geo_query": (
                _resolve_geography_aliases(normalized_query)
                if normalized_query
                else normalized_query
            ),
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": self.ranking_profile,
        }
        request_body.update(sort_overrides)
        request_body.update(self._msm_request_fields)

        topic_ids = _topic_ids_from_filters(filters)
        if topic_ids and not sort_overrides:
            request_body["input.query(topic_q)"] = dict.fromkeys(topic_ids, 1.0)
            request_body["input.query(topic_weight)"] = self.topic_weight

        if self.passages_breadth_weight is not None and not sort_overrides:
            request_body["input.query(passages_breadth_weight)"] = (
                self.passages_breadth_weight
            )

        if self.debug:
            request_body["presentation.summary"] = "debug-summary"
        else:
            request_body["presentation.summary"] = "search"
        if not self.bolding:
            request_body["presentation.bolding"] = "false"

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="documents.search",
        )
        documents = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            # Map fields. Note: schema only has title, description.
            # source_url and original_document_id are required by Document.
            # We'll use the doc id for original_document_id and a dummy/empty source_url if missing.
            try:
                source = json.loads(fields.get("document_source"))
            except Exception:
                logger.warning(
                    "Document source could not be parsed for hit id=%r",
                    hit.get("id"),
                )
                continue
            labels = get_labels_from_vespa_response(source, fields)

            document_relationships = TypeAdapter(
                list[DocumentRelationship]
            ).validate_python(source.get("documents", []))

            documents.append(
                Document(
                    id=source.get("id", MISSING_PLACEHOLDER),
                    title=fields.get("title", MISSING_PLACEHOLDER),
                    description=fields.get("description", MISSING_PLACEHOLDER),
                    labels=labels,
                    attributes=source.get("attributes", {}),
                    documents=document_relationships,
                )
            )

            if self.debug:
                # NOTE: these are all fields that are stored as type summary in the index.
                # This is because overriding the default summary in the schema adds fields
                # to it, rather than redefining the schema from scratch.
                _STANDARD_FIELDS = {
                    "document_source",
                    "sddocname",
                    "documentid",
                    "summaryfeatures",
                    "title",
                    "description",
                    "labels",
                    "passages",
                    "passages_text",
                }
                hit_debug = {
                    k: v for k, v in fields.items() if k not in _STANDARD_FIELDS
                }
                hit_debug["relevance"] = hit.get("relevance")
                hit_debug["summaryfeatures"] = fields.get("summaryfeatures")
                debug_info.append(hit_debug)

        self.last_debug_info = debug_info
        if self.debug and debug_info:
            logger.info(
                "Debug info for %d document hits:\n%s",
                len(debug_info),
                json.dumps(debug_info, indent=2),
            )

        total_size = _get_total_count(response)
        return ListResponse(
            results=documents, total_size=total_size, next_page_token=None
        )

    def get(self, document_id: str) -> Document | None:
        """Fetch a single document by id, parsed from its stored document_source."""
        endpoint = f"{self.settings.vespa_endpoint}/document/v1/documents/documents/docid/{document_id}"
        logger.info("Vespa request started [documents.get]")
        try:
            response = requests.get(
                endpoint,
                timeout=API_TIMEOUT,
                headers={"Authorization": f"Bearer {self.settings.vespa_read_token}"},
            )
        except Exception as exc:
            raise VespaError("Vespa request failed") from exc
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if response.status_code != HTTPStatus.OK:
            body_preview = (response.text or "")[:HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS]
            raise VespaError(
                f"Vespa returned status {response.status_code}: {body_preview}"
            )

        fields = response.json().get("fields", {})
        document_source = fields.get("document_source")
        if not document_source:
            return None

        # Rendered the same way as a search hit: concepts are fed onto the Vespa
        # document as a partial update, so they only exist in `fields`.
        source = json.loads(document_source)
        document = Document.model_validate(source)
        document.labels = get_labels_from_vespa_response(source, fields)
        return document

    @staticmethod
    def parse_label_type_id_value(s: str) -> tuple[str, str, str]:
        """
        Parse a `{type}::{id}::{value}` string into its three components.

        {id} may contain `::`
        e.g: `geography::geography::USA::United States of America`
        """
        label_type, _, label_id_value = s.partition("::")
        label_id, _, label_value = label_id_value.rpartition("::")
        return label_type, label_id, label_value

    def aggregations(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> list[CountAggregation[Label]]:
        """Return aggregations (label/concept groups with counts) filtered by the search query."""
        if query:
            query = _strip_quotes(query)
        # Build the top-level where clause from the search query and any filters,
        # mirroring how `search()` constructs its YQL.
        where = "true"
        if query:
            where += self._userQuery

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(
                filters,
                field_map=documents_filter_field_to_vespa_field_map,
                struct_map=documents_filter_struct_field_to_vespa_field_map,
            )

        # Group labels and concepts across all documents matching the search query.
        # The top-level `where` already scopes the document set.
        # per-bucket filtering is not needed here.
        grouping = G.all(
            G.all(
                G.group("labels_type_id_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
            G.all(
                G.group("concepts_type_id_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
        )

        # Build a raw YQL string, the same way `search()` does, because the query
        # builder's `.where()` only accepts Condition/bool objects, not raw strings.
        select_fields = (
            "labels_type_id_value_attribute, concepts_type_id_value_attribute"
        )
        groupby_str = str(grouping)
        yql = f"select {select_fields} from documents where {where} | {groupby_str}"

        request_body = {
            "yql": yql,
            "query": query,
            "geo_query": _resolve_geography_aliases(query) if query else query,
            "hits": 0,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": self.ranking_profile,
            **self._msm_request_fields,
        }
        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="documents.aggregations",
        )

        root = response.get("root", {})
        root_children: list[dict] = root.get("children") or []
        groups: list[dict] = (
            root_children[0].get("children", []) if root_children else []
        )

        group_values = []
        for group in groups:
            group_values.extend(group.get("children", []))

        count_aggregations: list[CountAggregation[Label]] = []
        for group_value in group_values:
            label_type_id_value = group_value.get("value", "")
            label_type, label_id, label_value = self.parse_label_type_id_value(
                label_type_id_value
            )
            count_aggregations.append(
                CountAggregation(
                    count=group_value.get("fields", {}).get("count()", 0),
                    value=Label(
                        id=label_id,
                        value=label_value,
                        type=label_type or MISSING_PLACEHOLDER,
                    ),
                )
            )
        return count_aggregations

    def _run_facet_query(
        self,
        query: str | None,
        where_filter: Filter | None,
        group_attributes: list[str],
    ) -> dict[str, dict[tuple[str, str], tuple[Label, int]]]:
        """Run a Vespa grouping query and return label/concept buckets partitioned by attribute."""
        if query:
            query = _strip_quotes(query)

        where = "true"
        if query:
            where += self._userQuery
        where += _build_filter_query(
            where_filter,
            field_map=documents_filter_field_to_vespa_field_map,
            struct_map=documents_filter_struct_field_to_vespa_field_map,
        )

        inner_groups = [
            G.all(
                G.group(attr),
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            )
            for attr in group_attributes
        ]
        grouping = G.all(*inner_groups)
        yql = f"select {', '.join(group_attributes)} from documents where {where} | {grouping}"

        request_body = {
            "yql": yql,
            "query": query,
            "geo_query": _resolve_geography_aliases(query) if query else query,
            "hits": 0,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": self.ranking_profile,
            **self._msm_request_fields,
        }
        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="documents.facets",
        )

        root_children: list[dict] = response.get("root", {}).get("children") or []
        groups: list[dict] = (
            root_children[0].get("children", []) if root_children else []
        )
        group_values: list[dict] = []
        for group in groups:
            group_values.extend(group.get("children", []))

        by_type: dict[str, dict[tuple[str, str], tuple[Label, int]]] = {}
        for gv in group_values:
            label_type, label_id, label_value = self.parse_label_type_id_value(
                gv.get("value", "")
            )
            label_type = label_type or MISSING_PLACEHOLDER
            count = gv.get("fields", {}).get("count()", 0)
            label = Label(id=label_id, value=label_value, type=label_type)
            by_type.setdefault(label_type, {})[(label_id, label_value)] = (
                label,
                count,
            )
        return by_type

    def labels_value_type_facets(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> dict[str, list[CountAggregation[Label]]]:
        """
        Compute disjunctive facet counts partitioned by `label.type`. AKA faceted search.

        The query generally coming across is
        - grouped by `label.type`
        - each filter within that is joined by `OR`
        - each group is joined by `AND`

        Example:
        - (category::1 OR category::2) OR (geography::USA OR geography::GBR)
        """
        filters = (
            Filter.model_validate_json(filters_json_string)
            if filters_json_string
            else None
        )

        facet_label_types = _get_label_types_from_filters(filters)
        facet_requests: dict[str, Filter | None] = {"filtered_labels": filters}
        for label_type in facet_label_types:
            facet_requests[f"filter_{label_type}"] = _prune_filter(
                filters,
                lambda c, t=label_type: _facet_filter_label_type(c) == t,
            )

        responses: dict[str, dict[str, dict[tuple[str, str], tuple[Label, int]]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(facet_requests))) as pool:
            futures = {
                pool.submit(
                    self._run_facet_query,
                    query,
                    plan,
                    [
                        "labels_type_id_value_attribute",
                        "concepts_type_id_value_attribute",
                    ],
                ): name
                for name, plan in facet_requests.items()
            }
            for future in as_completed(futures):
                responses[futures[future]] = future.result()

        result: dict[str, list[CountAggregation[Label]]] = {}
        for label_type, labels_for_type in responses["filtered_labels"].items():
            if label_type in facet_label_types:
                counts_for_type = responses[f"filter_{label_type}"].get(label_type, {})
            else:
                counts_for_type = labels_for_type

            entries: list[CountAggregation[Label]] = [
                CountAggregation(count=count, value=label)
                for label, count in counts_for_type.values()
            ]
            entries.sort(key=lambda c: -c.count)
            result[label_type] = entries

        return result

    def labels_type_facets(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> dict[str, list[CountAggregation[Label]]]:
        """Compute disjunctive facet counts partitioned by `label.relationship`."""
        filters = (
            Filter.model_validate_json(filters_json_string)
            if filters_json_string
            else None
        )

        facet_label_types = _get_label_types_from_filters(filters)
        facet_requests: dict[str, Filter | None] = {"filtered_labels": filters}
        for label_type in facet_label_types:
            facet_requests[f"filter_{label_type}"] = _prune_filter(
                filters,
                lambda c, t=label_type: _facet_filter_label_type(c) == t,
            )

        responses: dict[str, dict[str, dict[tuple[str, str], tuple[Label, int]]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(facet_requests))) as pool:
            futures = {
                pool.submit(
                    self._run_facet_query,
                    query,
                    plan,
                    ["labels_relationship_id_value_attribute"],
                ): name
                for name, plan in facet_requests.items()
            }
            for future in as_completed(futures):
                responses[futures[future]] = future.result()

        result: dict[str, list[CountAggregation[Label]]] = {}
        for label_type, labels_for_type in responses["filtered_labels"].items():
            if label_type in facet_label_types:
                counts_for_type = responses[f"filter_{label_type}"].get(label_type, {})
            else:
                counts_for_type = labels_for_type

            entries: list[CountAggregation[Label]] = [
                CountAggregation(count=count, value=label)
                for label, count in counts_for_type.values()
            ]
            entries.sort(key=lambda c: -c.count)
            result[label_type] = entries

        return result

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


class DevVespaPrincipalDocumentSearchEngine(DevVespaDocumentSearchEngine):
    """
    Search engine for principal documents.

    Overrides calls to .search with a filter for principal documents, so the engine
    can be used against relevance tests.
    """

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters_json_string: str | None = None,
    ) -> ListResponse[Document]:
        """Search principal documents"""

        principal_filter = Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id",
                    op="contains",
                    value="status::Principal",
                )
            ],
        )

        if filters_json_string is not None:
            caller_filter = Filter.model_validate_json(filters_json_string)
            merged_filter = Filter(op="and", filters=[principal_filter, caller_filter])
        else:
            merged_filter = principal_filter

        return super().search(
            query, pagination, order_by, merged_filter.model_dump_json()
        )

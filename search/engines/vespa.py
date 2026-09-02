import base64
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Generic, cast

from vespa.application import Vespa
from vespa.exceptions import VespaError
from vespa.io import VespaQueryResponse

from search import config
from search.aws import get_ssm_parameter
from search.data_in_models import Document as DocumentModel
from search.data_in_models import Item
from search.document import Document
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine, TModel
from search.engines.dev_vespa import (
    TOPIC_FILTER_FIELD,
    TOPIC_ID_PREFIX,
    Condition,
    FieldFilter,
    Filter,
    _format_value,
)
from search.label import Label
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


class VespaQueryError(Exception):
    """Raised when a query can't be built"""

    def __init__(self, message):
        super().__init__(f"Failed to build query: {message}")


class VespaErrorDetails:
    """
    Wrapper for VespaError that parses the arguments

    Copied from the CPR SDK.
    """

    def __init__(self, e: VespaError) -> None:
        self.e = e
        self.code = None
        self.summary = None
        self.message = None
        self.parse_args(self.e)

    def parse_args(self, e: VespaError) -> None:
        """
        Gets the details of the first error

        Args:
            e (VespaError): An error from the vespa python sdk
        """
        for arg in e.args:
            for error in arg:
                self.code = error.get("code")
                self.summary = error.get("summary")
                self.message = error.get("message")
                break

    @property
    def is_invalid_query_parameter(self) -> bool:
        """
        Checks if an error is coming from vespa on query parameters, see:

        https://github.com/vespa-engine/vespa/blob/0c55dc92a3bf889c67fac1ca855e6e33e1994904/
        container-core/src/main/java/com/yahoo/container/protect/Error.java
        """
        INVALID_QUERY_PARAMETER = 4
        return self.code == INVALID_QUERY_PARAMETER


class VespaSearchEngine(SearchEngine, ABC, Generic[TModel]):
    """Abstract search engine for connecting to Vespa."""

    VESPA_INSTANCE_URL_SSM_PARAMETER = "VESPA_INSTANCE_URL"
    VESPA_PUBLIC_CERT_SSM_PARAMETER = "VESPA_PUBLIC_CERT_READ_ONLY"
    VESPA_PRIVATE_KEY_SSM_PARAMETER = "VESPA_PRIVATE_KEY_READ_ONLY"

    DEFAULT_TIMEOUT_SECONDS: int = 20
    DEFAULT_RANKING_SOFTTIMEOUT_FACTOR: str = "0.7"
    DEFAULT_SUMMARY: str = "search_summary"

    def __init__(self) -> None:
        self.client: Vespa | None = None
        self._temp_dir = TemporaryDirectory()
        self.cert_dir = Path(self._temp_dir.name)

    def connect_to_vespa(
        self,
    ):
        """
        Connect to Vespa using read-only credentials. Sets self.client.

        Saves local files required for auth to cert_dir.
        """

        vespa_instance_url = get_ssm_parameter(config.vespa_url_ssm_key)
        vespa_public_cert_encoded = get_ssm_parameter(
            config.vespa_public_cert_read_only_ssm_key
        )
        vespa_private_key_encoded = get_ssm_parameter(
            config.vespa_private_key_read_only_ssm_key
        )

        vespa_public_cert = base64.b64decode(vespa_public_cert_encoded).decode("utf-8")
        vespa_private_key = base64.b64decode(vespa_private_key_encoded).decode("utf-8")

        cert_path = self.cert_dir / "cert.pem"
        key_path = self.cert_dir / "key.pem"

        with open(cert_path, "w", encoding="utf-8") as f:
            f.write(vespa_public_cert)

        with open(key_path, "w", encoding="utf-8") as f:
            f.write(vespa_private_key)

        self.client = Vespa(
            url=vespa_instance_url,
            cert=str(cert_path),
            key=str(key_path),
        )

    def search(
        self,
        query: str,
        pagination: Pagination,
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None = None,
    ) -> ListResponse[TModel]:
        """
        Search Vespa using the configured search strategy.

        :param query: Search query from the user
        :param filters_json_string: Filters JSON string
        :param pagination: Pagination
        :return: List of model objects matching the search.
        """
        if self.client is None:
            self.connect_to_vespa()
            assert self.client is not None  # nosec

        request_body = self._build_request(query, pagination, filters_json_string)

        try:
            vespa_response = cast(
                VespaQueryResponse, self.client.query(body=request_body)
            )
        except VespaError as e:
            err_details = VespaErrorDetails(e)
            if err_details.is_invalid_query_parameter:
                logger.error(err_details.message)
                raise VespaQueryError(err_details.summary)
            else:
                raise e

        return self._parse_vespa_response(vespa_response)

    @abstractmethod
    def _build_request(
        self, query: str, pagination: Pagination, filters_json_string: str | None
    ) -> dict[str, Any]:
        """
        Build the Vespa query request body.

        :param query: Search query from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: Dictionary containing the Vespa query request body.
        """
        ...

    @abstractmethod
    def _parse_vespa_response(
        self, response: VespaQueryResponse
    ) -> ListResponse[TModel]:
        """
        Parse a Vespa query response into model objects.

        :param response: The raw Vespa query response.
        :return: List of parsed model objects.
        """
        ...

    def count(self, query: str) -> int:
        """
        Count search results.

        Not yet implemented.
        """
        raise NotImplementedError()


class VespaDocumentSearchEngine(VespaSearchEngine[DocumentModel], ABC):
    """
    Abstract base class for Vespa document search engines.

    Searches the ``family_document`` schema in Vespa. Subclasses must implement
    :meth:`_build_request` to define their search strategy.
    """

    model_class = DocumentModel

    def _parse_vespa_response(
        self, response: VespaQueryResponse
    ) -> ListResponse[DocumentModel]:
        """Parse a Vespa query response into Document objects."""
        documents = []

        root = response.json.get("root", {})
        children = root.get("children", [])

        for child in children:
            fields = child.get("fields", {})

            document_title = fields.get("document_title", "")
            family_description = fields.get("family_description", "")
            document_source_url = fields.get("document_source_url", "")
            document_import_id = fields.get("document_import_id", "")

            document = DocumentModel(
                title=document_title,
                items=[Item(url=document_source_url)],
                description=family_description,
                id=document_import_id,
            )
            documents.append(document)

        return ListResponse(
            results=documents,
            total_size=len(documents),
            next_page_token=None,
        )


# Filters reach the engines in the dev-Vespa vocabulary
# (:class:`search.engines.dev_vespa.Filter`), which names fields after the
# ``passages`` schema. The engines below query the ``document_passage`` schema,
# which names the same things differently, so the conditions need translating.
#
# Fields with no ``document_passage`` equivalent raise rather than being dropped:
# a silently dropped filter returns unscoped results that still look valid.
_PASSAGE_FILTER_FIELD_MAP: dict[str, str] = {
    "document_id": "document_import_id",
}

# `concepts.id` on `document_passage` holds the bare wikibase id (e.g. "Q1829"),
# where `passages` stores it on `labels.value.id` with a `concept::` prefix.
_PASSAGE_TOPIC_FIELD = "concepts.id"


def _passage_condition_yql(condition: Condition) -> str:
    """Translate a single filter condition into ``document_passage`` YQL."""
    if not isinstance(condition, FieldFilter):
        raise VespaQueryError(
            f"{type(condition).__name__} filters are not supported on document_passage"
        )

    if condition.field == TOPIC_FILTER_FIELD:
        # Corpus filters share this field but use an `agent::` prefix, and there
        # is no provider field on `document_passage` to map them onto.
        if not (
            isinstance(condition.value, str)
            and condition.value.startswith(TOPIC_ID_PREFIX)
        ):
            raise VespaQueryError(
                f"only {TOPIC_ID_PREFIX!r} values of {TOPIC_FILTER_FIELD!r} are "
                f"supported on document_passage, got {condition.value!r}"
            )
        vespa_field = _PASSAGE_TOPIC_FIELD
        value: str | float | bool = condition.value.removeprefix(TOPIC_ID_PREFIX)
    elif condition.field in _PASSAGE_FILTER_FIELD_MAP:
        vespa_field = _PASSAGE_FILTER_FIELD_MAP[condition.field]
        value = condition.value
    else:
        raise VespaQueryError(
            f"filter field {condition.field!r} has no document_passage equivalent"
        )

    expr = f"{vespa_field} contains {_format_value(value)}"
    return f"!({expr})" if condition.op == "not_contains" else expr


def _build_passage_filter_yql(filter_group: Filter) -> str:
    """
    Recursively build ``document_passage`` YQL for a filter group.

    Unlike the ``passages`` schema this needs no ``sameElement`` grouping: two
    topics ANDed as ``concepts.id contains "Q567" and concepts.id contains
    "Q1651"`` already mean "the passage carries both concepts", each possibly on
    a different element of the array.
    """
    parts = [
        _build_passage_filter_yql(item)
        if isinstance(item, Filter)
        else _passage_condition_yql(item)
        for item in filter_group.filters
    ]
    parts = [part for part in parts if part]
    if not parts:
        return ""

    joined = f" {filter_group.op} ".join(parts)
    return f"({joined})" if len(parts) > 1 else joined


class VespaPassageSearchEngine(VespaSearchEngine[Passage], ABC):
    """
    Abstract base class for Vespa passage search engines.

    Subclasses must implement _build_request() to define their search strategy.
    """

    model_class = Passage

    @staticmethod
    def _build_where_clause(
        search_term_yql: str, filters_json_string: str | None
    ) -> str:
        """Combine the search-term clause with any filters."""
        parts = [search_term_yql] if search_term_yql else []
        if filters_json_string:
            filter_yql = _build_passage_filter_yql(
                Filter.model_validate_json(filters_json_string)
            )
            if filter_yql:
                parts.append(filter_yql)
        # A query with neither terms nor filters still needs a match-all clause.
        return " and ".join(parts) if parts else "true"

    def _parse_vespa_response(
        self, response: VespaQueryResponse
    ) -> ListResponse[Passage]:
        """Parse a Vespa query response with summary ``search_summary``."""
        passages = []

        root = response.json.get("root", {})
        children = root.get("children", [])

        for child in children:
            fields = child.get("fields", {})

            text = fields.get("text_block", "")
            text_block_id = fields.get("text_block_id", "")

            family_name = fields.get("family_name", "")
            family_description = fields.get("family_description", "")
            document_source_url = fields.get("document_source_url", "")
            document_import_id = fields.get("document_import_id", "")

            document = Document(
                title=family_name,
                source_url=document_source_url,
                description=family_description,
                original_document_id=document_import_id,
                labels=[],
            )

            passage = Passage(
                text_block_id=text_block_id,
                text=text,
                document_id=document.id,
            )
            passages.append(passage)

        return ListResponse(
            results=passages,
            total_size=len(passages),
            next_page_token=None,
        )


class ExactVespaPassageSearchEngine(VespaPassageSearchEngine):
    """
    Vespa search engine using exact text matching without stemming.

    Uses the text_block_not_stemmed field with stem:false for precise
    text matching. Ranking profile: exact_not_stemmed.
    """

    def _build_request(
        self,
        query: str,
        pagination: Pagination,
        filters_json_string: str | None,
    ) -> dict[str, Any]:
        """
        Build request body for exact match search.

        :param query: Search query from the user. May be empty, for a
            filters-only search.
        :param pagination: Pagination
        :param filters_json_string: Filters JSON string
        :return: Dictionary containing the Vespa query request body
        """
        search_term = (
            "(text_block_not_stemmed contains ({stem: false}@query_string))"
            if query
            else ""
        )
        where = self._build_where_clause(search_term, filters_json_string)
        yql = f"select * from sources document_passage where {where}"

        logger.info("🔎 Passage search query built (query=%r, yql=%s)", query, yql)

        request_body: dict[str, Any] = {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "ranking.profile": "exact_not_stemmed",
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "summary": self.DEFAULT_SUMMARY,
        }
        if query:
            request_body["query_string"] = query
        return request_body


class BM25TitleVespaDocumentSearchEngine(VespaDocumentSearchEngine):
    """
    Vespa document search engine that matches against document titles using BM25.

    Searches the ``family_document`` source using the ``document_title_index``
    field and the ``bm25_document_title`` ranking profile.
    """

    def _build_request(
        self,
        query: str,
        pagination: Pagination,
        filters_json_string: str | None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """
        Build request body for BM25 document title search.

        :param query: Search query from the user.
        :param limit: Maximum number of results to return.
        :param offset: Number of results to skip.
        :return: Dictionary containing the Vespa query request body.
        """
        yql = """
        select * from sources family_document where
            (document_title_index contains(@query_string))
        """

        return {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "query_string": query,
            "ranking.profile": "bm25_document_title",
            "summary": self.DEFAULT_SUMMARY,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
        }


class VespaLabelSearchEngine(VespaSearchEngine[Label]):
    """
    Vespa search engine for label search.

    Searches across preferred_label and description fields in the concept schema in
    Vespa. Alternative labels are returned in results but not currently searchable due
    to indexing limitations.
    """

    model_class = Label

    def _build_request(
        self,
        query: str,
        pagination: Pagination,
        filters_json_string: str | None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """
        Build request body for concept/label search.

        Searches across preferred_label and description (indexed fields) using text search.
        Alternative_labels are returned but not searched due to lack of indexing.

        :param terms: Search terms from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: Dictionary containing the Vespa query request body
        """
        yql = (
            "select * from sources concept where "
            "(preferred_label contains @query_string or description contains @query_string) "
        )

        return {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "query_string": query,
            "summary": self.DEFAULT_SUMMARY,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
        }

    def _parse_vespa_response(
        self, response: VespaQueryResponse
    ) -> ListResponse[Label]:
        """
        Parse a Vespa query response into Label objects.

        Extracts concept fields from Vespa and maps them to the Label model,
        ignoring wikibase-specific and relationship fields.

        :param response: The raw Vespa query response
        :return: List of Label objects
        """
        labels = []

        root = response.json.get("root", {})
        children = root.get("children", [])

        for child in children:
            fields = child.get("fields", {})
            alternative_labels = fields.get("alternative_labels", [])
            if not isinstance(alternative_labels, list):
                alternative_labels = []
            subconcept_labels = fields.get("subconcept_labels", [])
            if not isinstance(subconcept_labels, list):
                subconcept_labels = []
            label = Label(
                id=fields.get("id", ""),
                type=fields.get("type", ""),
                value=fields.get("value", ""),
                alternative_labels=alternative_labels,
                subconcept_labels=subconcept_labels,
            )
            labels.append(label)

        return ListResponse(
            results=labels,
            total_size=len(labels),
            next_page_token=None,
        )

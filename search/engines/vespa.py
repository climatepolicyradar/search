import base64
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Generic, cast

from vespa.application import Vespa
from vespa.exceptions import VespaError
from vespa.io import VespaQueryResponse

from search.aws import get_ssm_parameter
from search.document import Document
from search.engines import SearchEngine, TModel
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

    DEFAULT_SEARCH_LIMIT: int = 20
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

        vespa_instance_url = get_ssm_parameter(self.VESPA_INSTANCE_URL_SSM_PARAMETER)
        vespa_public_cert_encoded = get_ssm_parameter(
            self.VESPA_PUBLIC_CERT_SSM_PARAMETER
        )
        vespa_private_key_encoded = get_ssm_parameter(
            self.VESPA_PRIVATE_KEY_SSM_PARAMETER
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
        self, terms: str, limit: int | None = None, offset: int = 0
    ) -> list[TModel]:
        """
        Search Vespa using the configured search strategy.

        :param terms: Search terms from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: List of model objects matching the search.
        """
        if limit is None:
            logger.info(
                f"Search limit was not set. Setting to {self.DEFAULT_SEARCH_LIMIT}."
            )
            limit = self.DEFAULT_SEARCH_LIMIT

        if self.client is None:
            self.connect_to_vespa()
            assert self.client is not None

        request_body = self._build_request(terms, limit, offset)

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
    def _build_request(self, terms: str, limit: int, offset: int) -> dict[str, Any]:
        """
        Build the Vespa query request body.

        :param terms: Search terms from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: Dictionary containing the Vespa query request body.
        """
        ...

    @abstractmethod
    def _parse_vespa_response(self, response: VespaQueryResponse) -> list[TModel]:
        """
        Parse a Vespa query response into model objects.

        :param response: The raw Vespa query response.
        :return: List of parsed model objects.
        """
        ...

    def count(self, terms: str) -> int:
        """
        Count search results.

        Not yet implemented.
        """
        raise NotImplementedError()


class VespaDocumentSearchEngine(VespaSearchEngine[Document], ABC):
    """
    Abstract base class for Vespa document search engines.

    Searches the ``family_document`` schema in Vespa, returning
    :class:`~search.document.Document` instances. Subclasses must implement
    :meth:`_build_request` to define their search strategy.
    """

    model_class = Document

    def _parse_vespa_response(self, response: VespaQueryResponse) -> list[Document]:
        """Parse a Vespa query response into Document objects."""
        documents = []

        root = response.json.get("root", {})
        children = root.get("children", [])

        for child in children:
            fields = child.get("fields", {})

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
            documents.append(document)

        return documents


class VespaPassageSearchEngine(VespaSearchEngine[Passage], ABC):
    """
    Abstract base class for Vespa passage search engines.

    Subclasses must implement _build_request() to define their search strategy.
    """

    model_class = Passage

    def _parse_vespa_response(self, response: VespaQueryResponse) -> list[Passage]:
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
                text=text,
                document_id=document.id,
                labels=[],
                original_passage_id=text_block_id,
            )
            passages.append(passage)

        return passages


class ExactVespaPassageSearchEngine(VespaPassageSearchEngine):
    """
    Vespa search engine using exact text matching without stemming.

    Uses the text_block_not_stemmed field with stem:false for precise
    text matching. Ranking profile: exact_not_stemmed.
    """

    def _build_request(self, terms: str, limit: int, offset: int) -> dict[str, Any]:
        """
        Build request body for exact match search.

        :param terms: Search terms from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: Dictionary containing the Vespa query request body
        """
        yql = f"""
        select * from sources document_passage where
            (text_block_not_stemmed contains ({{stem: false}}@query_string))
        limit {limit} offset {offset}
        """

        return {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "query_string": terms,
            "ranking.profile": "exact_not_stemmed",
            "summary": self.DEFAULT_SUMMARY,
        }


class HybridVespaPassageSearchEngine(VespaPassageSearchEngine):
    """
    Vespa search engine combining text search with semantic embeddings.

    Uses userInput for text search combined with nearestNeighbor for
    embedding-based semantic search. Uses msmarco-distilbert-dot-v5
    embedding model. Ranking profile: hybrid.
    """

    EMBEDDING_MODEL: str = "msmarco-distilbert-dot-v5"
    DISTANCE_THRESHOLD: float = 0.24
    TARGET_NUM_HITS: int = 1000

    def _build_request(self, terms: str, limit: int, offset: int) -> dict[str, Any]:
        """
        Build request body for hybrid search (text + embeddings).

        :param terms: Search terms from the user
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: Dictionary containing the Vespa query request body
        """
        yql = f"""
        select * from sources document_passage where
            (
                (userInput(@query_string)) or
                ([{{"targetNumHits": {self.TARGET_NUM_HITS}, "distanceThreshold": {self.DISTANCE_THRESHOLD}}}]
                 nearestNeighbor(text_embedding,query_embedding))
            )
        limit {limit} offset {offset}
        """

        return {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "query_string": terms,
            "ranking.profile": "hybrid",
            "input.query(query_embedding)": f"embed({self.EMBEDDING_MODEL}, @query_string)",
            "summary": self.DEFAULT_SUMMARY,
        }


class BM25TitleVespaDocumentSearchEngine(VespaDocumentSearchEngine):
    """
    Vespa document search engine that matches against document titles using BM25.

    Searches the ``family_document`` source using the ``document_title_index``
    field and the ``bm25_document_title`` ranking profile.
    """

    def _build_request(self, terms: str, limit: int, offset: int) -> dict[str, Any]:
        """
        Build request body for BM25 document title search.

        :param terms: Search terms from the user.
        :param limit: Maximum number of results to return.
        :param offset: Number of results to skip.
        :return: Dictionary containing the Vespa query request body.
        """
        yql = f"""
        select * from sources family_document where
            (document_title_index contains(@query_string))
        limit {limit} offset {offset}
        """

        return {
            "yql": yql,
            "timeout": str(self.DEFAULT_TIMEOUT_SECONDS),
            "ranking.softtimeout.factor": self.DEFAULT_RANKING_SOFTTIMEOUT_FACTOR,
            "query_string": terms,
            "ranking.profile": "bm25_document_title",
            "summary": self.DEFAULT_SUMMARY,
        }

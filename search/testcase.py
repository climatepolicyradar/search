import re
from abc import ABC, abstractmethod
from typing import Callable, Generic, Literal, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from search.data_in_models import Document
from search.engines import Pagination, SearchEngine
from search.label import Label
from search.passage import Passage

TModel = TypeVar("TModel", Label, Passage, Document)


class TestCase(BaseModel, ABC, Generic[TModel]):
    """A test case"""

    __test__ = False

    category: str | None = None
    search_terms: str
    description: str

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        """Normalize category: convert to lowercase with underscores."""
        if value is None:
            return value
        return value.strip().lower().replace("-", "_").replace(" ", "_")

    @property
    def name(self) -> str:
        """The name of the test case type (its class name)"""
        return self.__class__.__name__

    def diagnose(self, search_results: list[TModel]) -> str:  # noqa: ARG002
        """
        Return a diagnostic string explaining a test failure.

        :param search_results: The search results returned by the engine.
        :returns: A human-readable string describing why the test likely failed.
        """
        return ""

    @abstractmethod
    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        raise NotImplementedError

    @computed_field
    @property
    @abstractmethod
    def id(self) -> Identifier:
        """Generated ID for a TestCase"""

        raise NotImplementedError


class PrecisionTestCase(TestCase[TModel], Generic[TModel]):
    """Dictates which should be the top results for a given search"""

    expected_result_ids: list[str] = Field(
        description="The expected IDs for the top results."
    )
    strict_order: bool = Field(
        description=(
            "Whether the expected family slugs should be in the exact order specified."
        ),
        default=False,
    )

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(
            query=self.search_terms,
            pagination=Pagination(page_token=1, page_size=10),
            filters_json_string=None,
        )
        result_ids = [result.id for result in search_results.results]

        result_ids_limited = result_ids[: len(self.expected_result_ids)]

        if self.strict_order:
            passed = self.expected_result_ids == result_ids_limited
        else:
            passed = sorted(self.expected_result_ids) == sorted(result_ids_limited)

        return passed, search_results.results

    def diagnose(self, search_results: list[TModel]) -> str:
        """
        Return diagnostic info for a precision test failure.

        :param search_results: The search results returned by the engine.
        :returns: A string showing where expected IDs actually ranked.
        """
        result_ids = [result.id for result in search_results]
        id_to_rank = {rid: i + 1 for i, rid in enumerate(result_ids)}
        n = len(self.expected_result_ids)

        lines = [f"Expected top {n} results (strict_order={self.strict_order}):"]
        for i, expected_id in enumerate(self.expected_result_ids):
            expected_rank = i + 1
            actual_rank = id_to_rank.get(expected_id)
            if actual_rank is None:
                lines.append(
                    f"  '{expected_id}': expected rank {expected_rank}, "
                    f"not found in results"
                )
            else:
                lines.append(
                    f"  '{expected_id}': expected rank {expected_rank}, "
                    f"found at rank {actual_rank}"
                )

        actual_top = result_ids[:n]
        lines.append(f"Actual top {n}: {actual_top}")
        return "\n".join(lines)

    @model_validator(mode="after")
    def check_expected_result_ids_unique(self):
        """Check that the expected family slugs are unique."""
        if len(self.expected_result_ids) != len(set(self.expected_result_ids)):
            raise ValueError("expected_result_ids must be unique")
        return self

    @computed_field
    @property
    def id(self) -> Identifier:
        """Generated ID for a TestCase"""

        return Identifier.generate(
            self.name,
            self.category,
            self.search_terms,
            self.expected_result_ids,
            self.strict_order,
        )


class RecallTestCase(TestCase[TModel], Generic[TModel]):
    """Dictates which results should be anywhere in the top K results for a given search."""

    expected_result_ids: list[str] = Field(
        description="IDs which should appear in the top k results."
    )
    forbidden_result_ids: list[str] | None = Field(
        description="IDs which should not appear in the top k results.",
        default=None,
    )
    k: int = Field(
        description="The number of results to check for the expected results.",
        default=20,
        gt=0,
    )

    @model_validator(mode="after")
    def check_expected_result_ids_unique(self):
        """Check that the expected family slugs are unique."""
        if len(self.expected_result_ids) != len(set(self.expected_result_ids)):
            raise ValueError("expected_result_ids must be unique")
        return self

    @model_validator(mode="after")
    def check_forbidden_result_ids_unique(self):
        """Check that the expected family slugs are unique."""
        if self.forbidden_result_ids is not None and len(
            self.forbidden_result_ids
        ) != len(set(self.forbidden_result_ids)):
            raise ValueError("forbidden_result_ids must be unique")
        return self

    def diagnose(self, search_results: list[TModel]) -> str:
        """
        Return diagnostic info for a recall test failure.

        :param search_results: The search results returned by the engine.
        :returns: A string showing which expected IDs were found or missing,
            and any forbidden IDs that appeared.
        """
        result_ids = [result.id for result in search_results]
        id_to_rank = {rid: i + 1 for i, rid in enumerate(result_ids)}

        lines = [f"Recall check in top {self.k} results ({len(result_ids)} returned):"]

        missing = []
        found = []
        for expected_id in self.expected_result_ids:
            rank = id_to_rank.get(expected_id)
            if rank is None:
                missing.append(expected_id)
            else:
                found.append((expected_id, rank))

        if found:
            lines.append("  Found:")
            for eid, rank in found:
                lines.append(f"    '{eid}' at rank {rank}")
        if missing:
            lines.append("  Missing:")
            for eid in missing:
                lines.append(f"    '{eid}'")

        if self.forbidden_result_ids:
            forbidden_present = [
                (fid, id_to_rank[fid])
                for fid in self.forbidden_result_ids
                if fid in id_to_rank
            ]
            if forbidden_present:
                lines.append("  Forbidden IDs present:")
                for fid, rank in forbidden_present:
                    lines.append(f"    '{fid}' at rank {rank}")

        return "\n".join(lines)

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(
            query=self.search_terms,
            pagination=Pagination(page_token=1, page_size=10),
            filters_json_string=None,
        )
        result_ids = [result.id for result in search_results.results]

        expected_ids_not_in_response = set(self.expected_result_ids).difference(
            set(result_ids)
        )
        forbidden_ids_in_response = (
            set(self.forbidden_result_ids).intersection(set(result_ids))
            if self.forbidden_result_ids is not None
            else None
        )

        failed = expected_ids_not_in_response or forbidden_ids_in_response
        passed = not failed

        return passed, search_results.results

    @computed_field
    @property
    def id(self) -> Identifier:
        """Generated ID for a TestCase"""

        return Identifier.generate(
            self.name,
            self.category,
            self.search_terms,
            self.expected_result_ids,
            self.forbidden_result_ids,
            self.k,
        )


class FieldCharacteristicsTestCase(TestCase[TModel], Generic[TModel]):
    """Dictates characteristics that any or all of the top k results should have for a given search."""

    characteristics_test: Callable[[TModel], bool] = Field(
        description="A function which takes the primitive type as input and returns True if the expected characteristics for the field value are met, and False otherwise.",
        exclude=True,
    )
    k: int = Field(
        description="The number of results to check for the expected results.",
        default=20,
        gt=0,
    )
    all_or_any: Literal["all", "any"] = Field(
        description="Whether all or any of the results should match the test characteristics.",
        default="all",
    )
    assert_results: bool = Field(
        description="Whether to assert that results should be returned for a search. Checks that more than 0 results are returned.",
        default=False,
    )

    def diagnose(self, search_results: list[TModel]) -> str:
        """
        Return diagnostic info for a field characteristics test failure.

        :param search_results: The search results returned by the engine.
        :returns: A string showing how many results passed or failed the
            characteristics test.
        """
        total = len(search_results)
        passing = sum(1 for r in search_results if self.characteristics_test(r))
        failing = total - passing

        lines = [
            f"Characteristics test ({self.all_or_any} of {self.k}): "
            f"{passing}/{total} passed, {failing}/{total} failed"
        ]

        if self.k > len(search_results):
            "`k` chosen for test is greater than the number of search results returned. This will automatically fail this test."

        if self.assert_results and total == 0:
            lines.append("  No results returned (assert_results=True)")

        return "\n".join(lines)

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(
            query=self.search_terms,
            pagination=Pagination(page_token=1, page_size=self.k),
            filters_json_string=None,
        )

        if self.k > len(search_results.results):
            # self.diagnose handles reporting this kind of issue
            return False, search_results.results
        else:
            search_results = search_results.results[: self.k]
            passing_results = [
                result for result in search_results if self.characteristics_test(result)
            ]

        if self.all_or_any == "all":
            passed = len(passing_results) == len(search_results)
        elif self.all_or_any == "any":
            passed = len(passing_results) > 0

        if self.assert_results:
            passed = passed and (len(search_results) > 0)

        return passed, search_results

    @computed_field
    @property
    def id(self) -> Identifier:
        """Generated ID for a TestCase"""

        return Identifier.generate(
            self.name,
            self.category,
            self.search_terms,
            self.all_or_any,
            self.k,
        )


class SearchComparisonTestCase(TestCase[TModel], Generic[TModel]):
    """
    Compare two searches to each other. Compares the top k results.

    This test case runs two different searches and checks that they have a minimum
    proportion of overlapping results. Optionally, it can also check that the order
    of the overlapping results is the same.
    """

    search_terms_to_compare: str = Field(
        description="The terms to compare search_terms to."
    )
    k: int = Field(
        description="The number of results to compare.",
        default=20,
        gt=0,
    )
    minimum_overlap: float = Field(
        description="The desired proportion of the top k results which should overlap.",
        gt=0,
        le=1,
    )
    strict_order: bool = Field(
        description=(
            "Whether the overlapping results should be in the exact order specified."
        ),
        default=False,
    )

    @model_validator(mode="after")
    def check_comparison_terms(self):
        """Check that the comparison terms are different from the search terms."""
        if self.search_terms == self.search_terms_to_compare:
            raise ValueError(
                "search_terms and search_terms_to_compare must be different"
            )
        return self

    def diagnose(self, search_results: list[TModel]) -> str:
        """
        Return diagnostic info for a search comparison test failure.

        :param search_results: The search results from the first query.
            The second query's results are not available for diagnosis.
        :returns: A string showing comparison metadata and the first
            query's result IDs.
        """
        result_ids_1 = [r.id for r in search_results[: self.k]]
        lines = [
            f"Comparison: '{self.search_terms}' vs '{self.search_terms_to_compare}'",
            f"  Required overlap: {self.minimum_overlap:.0%} of top {self.k} "
            f"(strict_order={self.strict_order})",
            f"  Results for '{self.search_terms}': {result_ids_1}",
            "  (Second query results not stored; re-run to inspect)",
        ]
        return "\n".join(lines)

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results_1 = engine.search(
            query=self.search_terms,
            pagination=Pagination(page_token=1, page_size=self.k),
            filters_json_string=None,
        )
        search_results_2 = engine.search(
            query=self.search_terms_to_compare,
            pagination=Pagination(page_token=1, page_size=self.k),
            filters_json_string=None,
        )

        results_1_limited = search_results_1.results[: self.k]
        results_2_limited = search_results_2.results[: self.k]

        result_ids_1 = [result.id for result in results_1_limited]
        result_ids_2 = [result.id for result in results_2_limited]

        if self.strict_order:
            # Count matching IDs in the same positions
            overlap_count = sum(
                1 for id1, id2 in zip(result_ids_1, result_ids_2) if id1 == id2
            )
        else:
            # Count IDs that appear in both lists regardless of position
            overlap_count = len(set(result_ids_1).intersection(set(result_ids_2)))

        overlap_proportion = overlap_count / self.k if self.k > 0 else 0
        passed = overlap_proportion >= self.minimum_overlap

        return passed, search_results_1.results

    @computed_field
    @property
    def id(self) -> Identifier:
        """Generated ID for a TestCase"""

        return Identifier.generate(
            self.name,
            self.category,
            self.search_terms,
            self.search_terms_to_compare,
            self.minimum_overlap,
            self.strict_order,
            self.k,
        )


def all_words_in_string(include_words: list[str], string: str) -> bool:
    """Case-insensitive check for if all words are in a string, ignoring punctuation."""
    words = re.findall(r"\b\w+\b", string.lower())

    return all(word.lower() in words for word in include_words)


def any_words_in_string(include_words: list[str], string: str) -> bool:
    """Case-insensitive check for if any words are in a string."""
    words = re.findall(r"\b\w+\b", string.lower())

    return any(word.lower() in words for word in include_words)

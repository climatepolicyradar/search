from abc import ABC, abstractmethod
from typing import Callable, Generic, Literal, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from search.document import Document
from search.engines import SearchEngine
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

    expected_result_ids: list[Identifier | str] = Field(
        description="The expected IDs for the top results."
    )
    strict_order: bool = Field(
        description=(
            "Whether the expected family slugs should be in the exact order specified."
        ),
        default=False,
    )

    @field_validator("expected_result_ids", mode="before")
    @classmethod
    def coerce_identifiers(
        cls, value: list[str | Identifier] | None
    ) -> list[Identifier] | None:
        """
        Coerce string identifiers to Identifier objects.

        This validator allows strings to be passed in to `expected_result_ids`.
        """

        if value is None:
            return value

        return [Identifier(item) if isinstance(item, str) else item for item in value]

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(self.search_terms)
        result_ids = [result.id for result in search_results]

        result_ids_limited = result_ids[: len(self.expected_result_ids)]

        if self.strict_order:
            passed = self.expected_result_ids == result_ids_limited
        else:
            passed = sorted(self.expected_result_ids) == sorted(result_ids_limited)

        return passed, search_results

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

    expected_result_ids: list[Identifier | str] = Field(
        description="IDs which should appear in the top k results."
    )
    forbidden_result_ids: list[Identifier | str] | None = Field(
        description="IDs which should not appear in the top k results.",
        default=None,
    )
    k: int = Field(
        description="The number of results to check for the expected results.",
        default=20,
        gt=0,
    )

    @field_validator("expected_result_ids", "forbidden_result_ids", mode="before")
    @classmethod
    def coerce_identifiers(
        cls, value: list[str | Identifier] | None
    ) -> list[Identifier] | None:
        """
        Coerce string identifiers to Identifier objects.

        This validator allows strings to be passed in to `expected_result_ids`.
        """

        if value is None:
            return value

        return [Identifier(item) if isinstance(item, str) else item for item in value]

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

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(self.search_terms)
        result_ids = [result.id for result in search_results]

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

        return passed, search_results

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
        description="Whether all or any of the words in the search terms should be in the field value.",
        default="all",
    )

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""

        search_results = engine.search(self.search_terms)
        passing_results = [
            result for result in search_results if self.characteristics_test(result)
        ]

        if self.all_or_any == "all":
            passed = len(passing_results) == len(search_results)
        elif self.all_or_any == "any":
            passed = len(passing_results) > 0

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

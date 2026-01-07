import re
from typing import Self

from knowledge_graph.identifiers import Identifier


class IdentifierWithSuffix(Identifier):
    """
    An Identifier with an additional alphanumeric suffix.

    Format: 8-character base identifier + underscore + alphanumeric suffix
    Example: "2sgknw32_label"
    """

    # Override pattern as a compiled regex that includes the suffix
    pattern = re.compile(rf"^[{Identifier.valid_characters}]{{8}}_[a-zA-Z0-9]+$")

    def __new__(cls, value: str):
        """Validate the IdentifierWithSuffix string and create a new instance."""
        cls._validate(value)
        return str.__new__(cls, value)

    @classmethod
    def generate(cls, *args, suffix: str) -> Self:
        """
        Generate an IdentifierWithSuffix from input data and a suffix.

        Parameters
        ----------
        *args
            Input data used to generate the base identifier
        suffix : str
            The suffix to append to the base identifier

        Returns
        -------
        Self
            A new IdentifierWithSuffix instance
        """
        # Generate base identifier using parent class, but don't instantiate as IdentifierWithSuffix yet
        # This avoids validation error since the base identifier doesn't have a suffix
        base_id = Identifier.generate(*args)
        return cls(f"{base_id}_{suffix}")

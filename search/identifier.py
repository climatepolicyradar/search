import hashlib
import re
from typing import Any, Callable, Self

from pydantic import BaseModel
from pydantic_core import CoreSchema, core_schema


class Identifier(str):
    """
    A unique ID for a resource, comprised of 8 unambiguous lowercase and numeric characters.

    IDs are generated deterministically from input data, and look something like:
    ["2sgknw32", "gg7h2j2s", ...]

    With a set of 31 possible characters and 8 spaces in the ID, there's a total of
    31^8 = 852,891,037,441 available values in the space. This should be more than
    enough for most use cases!

    Usage:
      To generate an ID: `my_id = Identifier.generate("some", "data")`
      To cast/validate a string: `my_id = Identifier("abcdef12")` (raises ValueError if invalid)
    """

    # the following list of characters excludes "i", "l", "1", "o", "0" to minimise
    # ambiguity when people read the identifiers at a glance
    valid_characters = "abcdefghjkmnpqrstuvwxyz23456789"

    # Pattern needs to be defined using the literal string for valid_characters
    # as class attributes are resolved at class creation time.
    pattern = re.compile(rf"^[{valid_characters}]{{8}}$")

    def __new__(cls, value):
        """Validate the Identifier string and create a new instance."""
        cls._validate(value)
        return str.__new__(cls, value)

    @classmethod
    def generate(cls, *args) -> "Self":
        """Generates a new Identifier from the supplied data."""
        if not args:
            raise TypeError(
                f"{cls.__name__}.generate() requires at least one argument."
            )
        stringified_args = ""
        for arg in args:
            if isinstance(arg, BaseModel):
                stringified_args += arg.model_dump_json()
            else:
                stringified_args += str(arg)
        hashed_data = hashlib.sha256(stringified_args.encode()).digest()
        identifier = "".join(
            cls.valid_characters[b % len(cls.valid_characters)]
            for b in hashed_data[:8]  # Use first 8 bytes of hash
        )
        return cls(identifier)

    @classmethod
    def _validate(cls, value: str) -> str:
        """Validate that the Identifier string is in the correct format"""

        if not cls.pattern.match(value):
            raise ValueError(
                f"'{value}' is not a valid {cls.__name__}. Must be 8 characters from "
                f"the set '{cls.valid_characters}' (pattern: r'{cls.pattern.pattern}')."
            )
        return value

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: Callable[[Any], CoreSchema],  # type: ignore
    ) -> CoreSchema:
        """Returns a pydantic_core.CoreSchema object for Pydantic V2 compatibility."""
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.no_info_plain_validator_function(cls._validate),
        )

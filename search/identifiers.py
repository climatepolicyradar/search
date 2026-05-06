import hashlib
from typing import Any

from pydantic import BaseModel
from pydantic_core import CoreSchema, core_schema


class Identifier(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> CoreSchema:
        """Tells Pydantic to validate by calling Identifier(value), treating it as a str subclass"""
        return core_schema.no_info_plain_validator_function(cls)


def generate_id(*args: object) -> Identifier:
    data = "".join(
        a.model_dump_json() if isinstance(a, BaseModel) else str(a) for a in args
    )
    return Identifier(hashlib.sha256(data.encode()).hexdigest()[:8])

from typing import Sequence

from pydantic import BaseModel


def serialise_pydantic_list_as_jsonl[T: BaseModel](models: Sequence[T]) -> str:
    """
    Serialize a list of Pydantic models as JSONL (JSON Lines) format.

    Each model is serialized on a separate line using model_dump_json().
    """
    jsonl_content = "\n".join(model.model_dump_json() for model in models)

    return jsonl_content

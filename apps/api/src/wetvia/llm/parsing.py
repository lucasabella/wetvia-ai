"""Validate model output and retry once with the validation error."""

from collections.abc import Awaitable, Callable, Sequence

from pydantic import BaseModel, ValidationError

from wetvia.llm.ports import ChatMessage

Complete = Callable[[Sequence[ChatMessage]], Awaitable[str]]


def validation_feedback(exc: ValidationError, raw: str) -> str:
    return (
        "Validation failed: "
        f"{exc}. "
        f"Previous output: {raw}. "
        "Reply with only JSON that matches the schema."
    )


async def parse_with_one_retry[ModelT: BaseModel](
    schema: type[ModelT],
    messages: Sequence[ChatMessage],
    complete: Complete,
    *,
    parse_json: Callable[[str], ModelT] | None = None,
) -> ModelT:
    parse = parse_json or schema.model_validate_json
    raw = await complete(messages)
    try:
        return parse(raw)
    except ValidationError as exc:
        corrected = (*messages, ChatMessage(role="user", content=validation_feedback(exc, raw)))
        second = await complete(corrected)
        return parse(second)

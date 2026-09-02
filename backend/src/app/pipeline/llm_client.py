"""Shared structured-extraction call used by every LLM-driven pipeline stage.

Structured output goes through forced tool-calling rather than a provider's
native "parse"/JSON-schema helper (e.g. OpenAI's response_format) — tool-calling
is the one mechanism confirmed to work across both configured providers
(OpenRouter's GLM 5.2 and Together.ai's DeepSeek V4 Pro); JSON-schema mode isn't
consistently documented across Together-hosted models, so it isn't the portable
choice here even though it exists.
"""

import json

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings


def _resolve_provider() -> tuple[str, str, str]:
    """Returns (base_url, api_key, model) for the active environment."""
    if settings.llm_env == "prod":
        return settings.together_base_url, settings.together_api_key, settings.together_model
    return settings.openrouter_base_url, settings.openrouter_api_key, settings.openrouter_model


def call_structured[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    *,
    tool_name: str,
    tool_description: str,
    client: OpenAI | None = None,
) -> T:
    base_url, api_key, model = _resolve_provider()
    client = client or OpenAI(base_url=base_url, api_key=api_key)

    tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": schema.model_json_schema(),
        },
    }
    # Plain dicts are structurally valid for these TypedDict params at runtime;
    # mypy's overload resolution doesn't narrow them from dict[str, str] /
    # dict[str, Any] without importing every specific TypedDict variant.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": tool_name}},
    )  # type: ignore[call-overload]
    message = response.choices[0].message
    if not message.tool_calls:
        raise RuntimeError(
            f"Expected a tool call, got none (finish_reason={response.choices[0].finish_reason})"
        )
    arguments = json.loads(message.tool_calls[0].function.arguments)
    return schema.model_validate(arguments)

"""Shared structured-extraction call used by every LLM-driven pipeline stage.

Structured output goes through forced tool-calling rather than a provider's
native "parse"/JSON-schema helper (e.g. OpenAI's response_format) — tool-calling
is the one mechanism confirmed to work across the configured providers
(OpenRouter's GLM 5.2 and Together.ai's DeepSeek V4 Pro; NVIDIA's build.nvidia.com
DeepSeek V4 Pro endpoint is OpenAI-compatible too but its tool-calling support
isn't yet confirmed — see Settings.llm_env docs); JSON-schema mode isn't
consistently documented across these providers, so it isn't the portable
choice here even though it exists.
"""

import json

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings


def _resolve_provider() -> tuple[str, str, str, dict[str, object]]:
    """Returns (base_url, api_key, model, extra_body) for the active environment.

    extra_body carries provider-specific request extensions. NVIDIA's free tier
    hosts DeepSeek V4 Pro as a reasoning model with extended "thinking" on by
    default — NVIDIA's own sample code disables it via chat_template_kwargs,
    and a real run left thinking on took 10+ minutes on that free tier before
    ever returning a tool call. Disabled here specifically for "nvidia" (a
    prototyping tier where speed matters more) — left on for "prod" (Together.ai,
    presumably better-provisioned), where the reasoning quality is worth the
    extra latency for the numbers that actually get reported.
    """
    if settings.llm_env == "prod":
        return settings.together_base_url, settings.together_api_key, settings.together_model, {}
    if settings.llm_env == "nvidia":
        return (
            settings.nvidia_base_url,
            settings.nvidia_api_key,
            settings.nvidia_model,
            {"chat_template_kwargs": {"thinking": False}},
        )
    return settings.openrouter_base_url, settings.openrouter_api_key, settings.openrouter_model, {}


def call_structured[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    *,
    tool_name: str,
    tool_description: str,
    client: OpenAI | None = None,
) -> T:
    base_url, api_key, model, extra_body = _resolve_provider()
    # Explicit timeout rather than the SDK's 10-minute default — a background
    # pipeline stage should fail fast and clearly rather than hang near-silently
    # (a run left with defaults sat "running" for 10+ minutes before this fix).
    client = client or OpenAI(base_url=base_url, api_key=api_key, timeout=120.0)

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
        extra_body=extra_body or None,
    )  # type: ignore[call-overload]
    message = response.choices[0].message
    if not message.tool_calls:
        raise RuntimeError(
            f"Expected a tool call, got none (finish_reason={response.choices[0].finish_reason})"
        )
    arguments = json.loads(message.tool_calls[0].function.arguments)
    return schema.model_validate(arguments)

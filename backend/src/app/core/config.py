from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import get_repo_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=get_repo_root() / ".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://auth_logic_hunter:auth_logic_hunter@localhost:5433/auth_logic_hunter"
    )

    # Which LLM environment the pipeline calls — defaults to "dev" so nobody
    # accidentally burns real money just by running the app. Switch deliberately
    # (env var LLM_ENV=...) for real evaluation runs or to try the "nvidia" tier.
    llm_env: Literal["dev", "nvidia", "prod"] = "dev"

    # Stage 3 <-> Stage 5 counterexample loop: max hypothesis-generation rounds
    # per run. A further round only happens if the previous one left refuted
    # (unsat/invalid) chains to feed back, so this bounds LLM calls, not forces them.
    hypothesis_rounds: int = 2

    # Dev: OpenRouter's free-tier GLM 5.2 — $0 cost, for pipeline iteration.
    # Confirmed: supports tools/tool_choice and JSON-schema structured output,
    # 256K context. Free tier is rate-limited by OpenRouter. Kept as the default
    # specifically because tool-calling is confirmed here — "nvidia" below is not
    # yet confirmed, so this stays the safe fallback until that's verified.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "z-ai/glm-5.2:free"

    # Nvidia: build.nvidia.com's free "prototyping" endpoint for DeepSeek V4
    # Pro — the SAME model as the "prod" tier below, so dev-testing here is
    # directly representative of real production behavior (unlike GLM 5.2,
    # which is a different model). Not yet the default: tool/function-calling
    # support isn't confirmed for this specific hosted endpoint, only for the
    # underlying model in general (Together.ai's listing) — verify before
    # relying on it. $0 cost, but "prototyping" tier — don't use for the
    # Phase 11 evaluation numbers even if it works, for reproducibility.
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "deepseek-ai/deepseek-v4-pro-0813"

    # Prod: Together.ai's DeepSeek V4 Pro — the real model for actual runs and
    # the Phase 11 evaluation numbers. Confirmed: function-calling support.
    # $1.32/1M input, $3.96/1M output at time of writing.
    together_api_key: str = ""
    together_base_url: str = "https://api.together.xyz/v1"
    together_model: str = "deepseek-ai/DeepSeek-V4-Pro-0813"


settings = Settings()

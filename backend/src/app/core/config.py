from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import get_repo_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=get_repo_root() / ".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://auth_logic_hunter:auth_logic_hunter@localhost:5433/auth_logic_hunter"

    # Which LLM environment the pipeline calls — defaults to "dev" so nobody
    # accidentally burns real money just by running the app. Switch to "prod"
    # deliberately (env var LLM_ENV=prod) for real evaluation runs.
    llm_env: Literal["dev", "prod"] = "dev"

    # Dev: OpenRouter's free-tier GLM 5.2 — $0 cost, for pipeline iteration.
    # Confirmed: supports tools/tool_choice and JSON-schema structured output,
    # 256K context. Free tier is rate-limited by OpenRouter.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "z-ai/glm-5.2:free"

    # Prod: Together.ai's DeepSeek V4 Pro — the real model for actual runs and
    # the Phase 11 evaluation numbers. Confirmed: function-calling support.
    # $1.32/1M input, $3.96/1M output at time of writing.
    together_api_key: str = ""
    together_base_url: str = "https://api.together.xyz/v1"
    together_model: str = "deepseek-ai/DeepSeek-V4-Pro-0813"


settings = Settings()

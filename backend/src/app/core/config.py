from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import get_repo_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=get_repo_root() / ".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://auth_logic_hunter:auth_logic_hunter@localhost:5433/auth_logic_hunter"
    anthropic_api_key: str = ""
    # Opus 5 for Stage 2 specifically — invariant extraction is the highest-stakes
    # reasoning step (everything downstream depends on it) and runs only a handful
    # of times per app, so the cost delta over Sonnet 5 is negligible. Sonnet 5
    # remains the default for higher-volume stages (Stage 3+).
    invariant_model: str = "claude-opus-5"
    # Sonnet 5 for Stage 3 — this stage runs many calls per run (one round per
    # invariant, plus the counterexample feedback loop once Stage 6 exists), where
    # Opus-tier cost would add up for no real accuracy gain: Z3 is what actually
    # filters bad hypotheses, not the LLM's own confidence.
    hypothesis_model: str = "claude-sonnet-5"


settings = Settings()

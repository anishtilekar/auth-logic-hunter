from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import get_repo_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=get_repo_root() / ".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://auth_logic_hunter:auth_logic_hunter@localhost:5433/auth_logic_hunter"
    anthropic_api_key: str = ""


settings = Settings()

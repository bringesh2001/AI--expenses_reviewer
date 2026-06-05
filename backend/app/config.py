from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_jwt_secret: str

    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    cors_origins: str = "http://localhost:5173"

    extraction_model: str = "claude-haiku-4-5-20251001"
    reasoning_model: str = "claude-sonnet-4-6"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024

    min_retrieval_score: float = 0.65
    min_confidence: float = 0.50
    retrieval_top_k: int = 10
    rerank_top_k: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: SecretStr = Field(..., description="Chave da API Groq")
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Modelo Groq a usar",
    )
    groq_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    groq_max_tokens: int = Field(default=1024, ge=128, le=8192)

    database_url: str = Field(
        default="postgresql://text2sql:text2sql@localhost:54321/text2sql_db",
    )

    sql_blocked_keywords: list[str] = Field(
        default=["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE",
                 "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"],
    )
    sql_max_rows: int = Field(default=500, description="Limite de linhas retornadas")
    sql_timeout_seconds: int = Field(default=10)

    app_title: str = "Text-to-SQL · Análise por Linguagem Natural"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cache_ttl_seconds: int = Field(default=300, description="TTL do cache de queries")

    @field_validator("groq_model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        allowed = {
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        }
        if v not in allowed:
            raise ValueError(f"Modelo '{v}' não suportado. Use: {allowed}")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ValueError("DATABASE_URL deve ser PostgreSQL")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — carregado uma vez, reutilizado em toda a app."""
    return Settings()

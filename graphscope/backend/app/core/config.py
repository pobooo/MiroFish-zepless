from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GraphScope"
    api_prefix: str = "/api"
    debug: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:4173",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
        ]
    )

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str | None = None

    default_group_id: str | None = None
    cache_ttl_seconds: int = 300
    shortest_path_cutoff: int = 6
    graph_source_mode: Literal["graphiti", "generic"] = "graphiti"

    model_config = SettingsConfigDict(
        env_prefix="GRAPHSCOPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

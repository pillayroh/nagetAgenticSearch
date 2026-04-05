from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Default false: no local Mongo required (per-request URL cache + in-memory runs).
    use_mongodb: bool = False
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "agentic_search"

    tavily_api_key: str = ""
    # Tavily topic filter: general | news | finance (empty = default general)
    tavily_topic: str = ""
    mock_search: bool = False
    snippet_first: bool = True
    snippet_first_min_chars: int = 280
    always_fetch_top_n: int = Field(default=5, ge=0, le=25)

    # llm_backend: huggingface (InferenceClient + text_generation) | openai (chat completions)
    llm_backend: str = "huggingface"
    hf_inference_provider: str = "featherless-ai"
    hf_token: str = ""

    # OpenAI-compatible API when llm_backend=openai
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    llm_json_object: bool = True
    llm_max_tokens: int = 4096
    llm_max_evidence_chars: int = 28000
    llm_max_entities: int = 8

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    scrape_timeout_s: float = 20.0
    max_concurrent_fetches: int = 5

    search_max_results: int = 15
    search_chunk_chars: int = 3000
    search_max_chunks_per_url: int = 2

    @field_validator(
        "tavily_api_key",
        "tavily_topic",
        "llm_model",
        "llm_base_url",
        "llm_api_key",
        "llm_backend",
        "hf_inference_provider",
        "hf_token",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

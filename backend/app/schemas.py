from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int | None = Field(default=None, ge=1, le=30)


class SearchResponse(BaseModel):
    run_id: str
    query: str
    column_order: list[str]
    entities: list[dict[str, Any]]
    search_urls: list[str]
    meta: dict[str, Any] = Field(default_factory=dict)

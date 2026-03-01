from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RecPlaceV2(BaseModel):
    id: str
    name: str
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    summary: str | None = None
    image_urls: list[str] | None = Field(default=None, alias="imageUrls")
    image_url: str | None = Field(default=None, alias="imageUrl")
    distance_km: float | None = None
    eta_minutes: int | None = None
    open_status: Literal[
        "open", "closing_soon", "opens_soon", "closed", "unknown"
    ] = "unknown"
    open_until: str | None = None
    next_open_time: str | None = None
    rating: float | None = None
    review_count: int | None = None
    price_level: str | None = None
    reasons: list[str] | None = None

    model_config = {"populate_by_name": True}


class Coverage(BaseModel):
    requested_results: int | None = None
    returned_results: int | None = None
    theme_coverage: str | None = None
    notes: str | None = None


class InstantRecommendations(BaseModel):
    theme: str | None = None
    now_local: str | None = None
    transport_mode: str | None = None
    results: list[RecPlaceV2]
    coverage: Coverage | None = None


class InstantRequest(BaseModel):
    instant_id: int = Field(alias="instantId")
    location: dict | None = None
    k: int = 5
    transport_mode: str = Field(default="walking", alias="transportMode")
    max_distance_km: float = Field(default=2.0, alias="maxDistanceKm")
    now_local: str | None = Field(default=None, alias="nowLocal")
    language: str = "en"

    model_config = {"populate_by_name": True}

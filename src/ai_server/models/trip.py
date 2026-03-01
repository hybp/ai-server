from __future__ import annotations

from pydantic import BaseModel, Field


class Place(BaseModel):
    name: str = Field(description="displayName of the place")
    id: str = Field(description="Google Place id")


class DayPlan(BaseModel):
    day: int
    destinations: list[Place]


class TripPlan(BaseModel):
    days: list[DayPlan]


class TripPlanRequest(BaseModel):
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    regions: list[str] = Field(default_factory=lambda: ["Hong Kong"])
    categories: list[str] = Field(default_factory=list)
    group_type: str = Field(default="", alias="groupType")

    model_config = {"populate_by_name": True}

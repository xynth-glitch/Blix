"""AI assistant request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from blix.models.canonical import NearbyStop, Route, RouteDetails, StopArrival


class AssistantLocation(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    location: AssistantLocation | None = None
    destination: str | None = Field(default=None, max_length=200)


class AssistantContext(BaseModel):
    routes: list[Route] = Field(default_factory=list)
    route_details: list[RouteDetails] = Field(default_factory=list)
    nearby_stops: list[NearbyStop] = Field(default_factory=list)
    arrivals: dict[str, list[StopArrival]] = Field(default_factory=dict)
    used_openai: bool = False


class AssistantResponse(BaseModel):
    answer: str
    context: AssistantContext

"""Grounded AI assistant for commuter questions.

The LLM is allowed to phrase and reason over context, but transport facts come
only from the deterministic engine. If OpenAI is not configured or unavailable,
we return a conservative grounded fallback from the same context.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from blix import engine
from blix.config import get_settings
from blix.models.assistant import AssistantContext, AssistantLocation, AssistantResponse
from blix.models.canonical import NearbyStop, Route, RouteDetails

_TRANSIT_KEYWORDS = {
    "bus",
    "route",
    "stop",
    "arrival",
    "arrive",
    "eta",
    "fare",
    "location",
    "destination",
    "nearby",
    "where",
    "dtc",
    "dimts",
    "travel",
    "commute",
}

_SYSTEM_PROMPT = """You are Blix, a Delhi public-bus assistant.
Stay on public-transport topics: route lookup, bus location, nearby stops,
arrivals, fares, and trip guidance.
Use only the JSON context provided by the backend for bus facts. Never invent
route numbers, stop names, ETAs, live locations, fares, or vehicle counts.
Every ETA/freshness statement must mention whether it is live, stale, scheduled,
or unknown.
If the user asks something outside transport, briefly steer them back to bus/trip
help.
If the context is insufficient, say what is missing and ask for a bus number,
destination, or current location.
Be concise, helpful, and clear for everyday commuters.
"""


def _looks_transit_related(message: str) -> bool:
    lower = message.lower()
    return any(word in lower for word in _TRANSIT_KEYWORDS)


def _collect_context(
    session: Session,
    message: str,
    location: AssistantLocation | None,
) -> AssistantContext:
    routes: list[Route] = []
    route_details: list[RouteDetails] = []
    nearby_stops: list[NearbyStop] = []
    arrivals = {}

    if _looks_transit_related(message):
        # Route search handles bus-number questions such as "764" or "tell me about 828AUP".
        routes = engine.search_routes(session, message, limit=5)
        if not routes:
            # Extract compact route-like tokens as a second pass.
            for token in message.replace("?", " ").replace(",", " ").split():
                if any(ch.isdigit() for ch in token) and 2 <= len(token) <= 12:
                    routes = engine.search_routes(session, token, limit=5)
                    if routes:
                        break

        for route in routes[:2]:
            details = engine.route_details(session, route.id)
            if details is not None:
                route_details.append(details)

    if location is not None:
        nearby_stops = engine.nearby_stops(session, location.lat, location.lon, limit=5)
        for nearby in nearby_stops[:3]:
            arrivals[nearby.stop.id] = engine.stop_arrivals(session, nearby.stop.id, limit=5)

    return AssistantContext(
        routes=routes,
        route_details=route_details,
        nearby_stops=nearby_stops,
        arrivals=arrivals,
    )


def _context_json(context: AssistantContext) -> str:
    return context.model_dump_json(mode="json", exclude_none=True)


def _fallback_answer(message: str, context: AssistantContext) -> str:
    if not _looks_transit_related(message):
        return (
            "I can help with Delhi bus routes, nearby stops, arrivals, fares, and trip "
            "questions. Ask me a bus number or where you want to go."
        )

    parts: list[str] = []
    if context.routes:
        route = context.routes[0]
        name = route.display_name
        details = context.route_details[0] if context.route_details else None
        parts.append(f"I found bus route {name} ({route.agency_id}).")
        if details:
            parts.append(f"It has {len(details.stops)} stops in the GTFS timeline.")
            if details.live_vehicles:
                parts.append(
                    f"There are {len(details.live_vehicles)} tracked vehicles; freshness is "
                    f"{details.live_vehicles[0].freshness}."
                )
            else:
                parts.append("I do not have a live vehicle position for it right now.")
    if context.nearby_stops:
        stops = ", ".join(
            f"{n.stop.name} ({round(n.distance_m)} m)" for n in context.nearby_stops[:3]
        )
        parts.append(f"Nearby stops: {stops}.")
    if not parts:
        parts.append(
            "I need a bus number, destination, or your current location to answer "
            "with GTFS-backed bus details."
        )
    return " ".join(parts)


def _extract_text(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(
                content.get("text"), str
            ):
                return content["text"]
    return None


async def answer(
    session: Session, message: str, location: AssistantLocation | None
) -> AssistantResponse:
    settings = get_settings()
    context = _collect_context(session, message, location)

    if not settings.openai_api_key:
        return AssistantResponse(answer=_fallback_answer(message, context), context=context)

    body = {
        "model": settings.openai_model,
        "instructions": _SYSTEM_PROMPT,
        "input": (
            f"User question: {message}\n\n"
            f"Grounding context JSON from Blix engine/GTFS/GTFS-RT:\n{_context_json(context)}"
        ),
        "max_output_tokens": 450,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
            resp = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=body,
            )
            resp.raise_for_status()
        text = _extract_text(resp.json())
        if text:
            context.used_openai = True
            return AssistantResponse(answer=text.strip(), context=context)
    except httpx.HTTPError:
        pass

    return AssistantResponse(answer=_fallback_answer(message, context), context=context)

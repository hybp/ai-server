"""Google Places search & backend detail fetching (async httpx)."""

from __future__ import annotations

import json
import logging
from math import atan2, cos, radians, sin, sqrt
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
MAX_RETRIES = 3

LAST_DETAIL_CACHE: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Location & category reference data
# ---------------------------------------------------------------------------

LOCATION_DATA: dict[str, dict[str, Any]] = {
    "Lantau West": {"region": "The New Territories", "latitude": 22.255, "longitude": 113.875, "radius": 8000},
    "Lantau East": {"region": "The New Territories", "latitude": 22.275, "longitude": 114.028, "radius": 8600},
    "Lamma": {"region": "The New Territories", "latitude": 22.21, "longitude": 114.125, "radius": 3200},
    "Tsing Yi": {"region": "The New Territories", "latitude": 22.348, "longitude": 114.1, "radius": 2000},
    "Kwai Tsing": {"region": "The New Territories", "latitude": 22.353, "longitude": 114.127, "radius": 2000},
    "North": {"region": "The New Territories", "latitude": 22.507, "longitude": 114.128, "radius": 4500},
    "Sai Kung": {"region": "The New Territories", "latitude": 22.35, "longitude": 114.31, "radius": 8500},
    "Sha Tin": {"region": "The New Territories", "latitude": 22.383, "longitude": 114.188, "radius": 4500},
    "Tai Po": {"region": "The New Territories", "latitude": 22.451, "longitude": 114.164, "radius": 3200},
    "Tsuen Wan": {"region": "The New Territories", "latitude": 22.39, "longitude": 114.114, "radius": 3500},
    "Tuen Mun": {"region": "The New Territories", "latitude": 22.391, "longitude": 113.976, "radius": 4000},
    "Yuen Long": {"region": "The New Territories", "latitude": 22.446, "longitude": 114.032, "radius": 4200},
    "Kowloon City": {"region": "Kowloon", "latitude": 22.32, "longitude": 114.19, "radius": 2000},
    "Kwun Tong": {"region": "Kowloon", "latitude": 22.307, "longitude": 114.23, "radius": 2300},
    "Sham Shui Po": {"region": "Kowloon", "latitude": 22.33, "longitude": 114.162, "radius": 1700},
    "Wong Tai Sin": {"region": "Kowloon", "latitude": 22.339, "longitude": 114.205, "radius": 2000},
    "Yau Tsim Mong": {"region": "Kowloon", "latitude": 22.304, "longitude": 114.172, "radius": 2000},
    "Kennedy Town": {"region": "Hong Kong Island", "latitude": 22.281, "longitude": 114.128, "radius": 1200},
    "Sheung Wan": {"region": "Hong Kong Island", "latitude": 22.286, "longitude": 114.15, "radius": 500},
    "Central": {"region": "Hong Kong Island", "latitude": 22.281, "longitude": 114.157, "radius": 1500},
    "Admiralty": {"region": "Hong Kong Island", "latitude": 22.28, "longitude": 114.165, "radius": 600},
    "Eastern": {"region": "Hong Kong Island", "latitude": 22.272, "longitude": 114.224, "radius": 2300},
    "Southern": {"region": "Hong Kong Island", "latitude": 22.216, "longitude": 114.204, "radius": 5300},
    "Wanchai": {"region": "Hong Kong Island", "latitude": 22.277, "longitude": 114.174, "radius": 1000},
    "Causeway Bay": {"region": "Hong Kong Island", "latitude": 22.277, "longitude": 114.19, "radius": 900},
    "Northpoint": {"region": "Hong Kong Island", "latitude": 22.291, "longitude": 114.2, "radius": 1000},
    "Hong Kong": {"region": "Entire Hong Kong", "latitude": 22.3193, "longitude": 114.1694, "radius": 20000},
}

TEXT_QUERY_DICT: dict[str, str | list[str]] = {
    "General": "Things to do",
    "Kid Friendly": "Kid friendly activities in hong kong",
    "Museums": "museum in hong kong",
    "Shopping": "shopping in hong kong",
    "Historical": "historical places in hong kong",
    "Outdoor Adventures": ["nature in hong kong", "beach in hong kong", "camping in hong kong"],
    "Art & Cultural": "arts in hong kong",
    "Amusement Parks": "Amusement parks in hong kong",
}

INSTANT_SEARCH_QUERIES: dict[int, list[str]] = {
    1: ["restaurants", "bars", "drink"],
    2: ["romantic places", "romantic cafes", "romantic restaurants"],
    3: ["museum", "art place", "tourist attraction", "movie theater", "cafe"],
    4: ["restaurants", "cafes", "local restaurants", "desserts"],
    5: ["parks", "hiking trails", "botanical gardens"],
    6: ["gyms", "yoga studios", "meditation centers"],
    7: ["shopping malls", "boutiques", "outlets"],
    8: ["clubs", "live music venues", "rooftop bars"],
    9: ["playgrounds", "indoor play areas", "kids' museums"],
    10: ["dog parks", "pet-friendly cafes", "pet stores"],
    11: ["free attractions", "cheap eats", "thrift stores"],
    12: ["seasonal festivals", "holiday markets", "fireworks displays"],
    13: ["spas", "tea houses", "hot springs"],
    14: ["kayaking", "go-kart tracks", "rock climbing gyms"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(seq or []))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def eta_minutes(distance_km: float, mode: str) -> int:
    speed = {"walking": 4.8, "public_transit": 12.0, "driving": 25.0}.get(mode, 4.8)
    return max(1, int(round((distance_km / speed) * 60)))


def _photo_media_url(photo_name: str, max_w: int = 1200) -> str:
    return (
        f"https://places.googleapis.com/v1/{photo_name}/media"
        f"?key={settings.google_api_key}&maxWidthPx={max_w}"
    )


# ---------------------------------------------------------------------------
# Google Places API
# ---------------------------------------------------------------------------


async def google_text_search(
    client: httpx.AsyncClient,
    query: str,
    lat: float,
    lon: float,
    radius: int = 2000,
    page_size: int = 10,
) -> list[str]:
    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY not set")
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_api_key,
        "X-Goog-FieldMask": "places.id",
    }
    body = {
        "textQuery": query,
        "languageCode": "en",
        "regionCode": "HK",
        "rankPreference": "RELEVANCE",
        "pageSize": page_size,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius,
            }
        },
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(url, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            places = resp.json().get("places", [])
            return [p["id"] for p in places if "id" in p]
        except httpx.HTTPError as e:
            logger.warning("google_text_search attempt %d failed: %s", attempt + 1, e)
    return []


async def google_place_details(client: httpx.AsyncClient, place_id: str) -> dict:
    if not settings.google_api_key:
        return {}

    url = (
        f"https://places.googleapis.com/v1/places/{place_id}"
        "?fields=id,displayName,shortFormattedAddress,formattedAddress,"
        "location,types,rating,userRatingCount,priceLevel,businessStatus,"
        "currentOpeningHours,regularOpeningHours,editorialSummary,photos.name"
        "&languageCode=en"
    )
    headers = {"X-Goog-Api-Key": settings.google_api_key}

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning("google_place_details %s attempt %d failed: %s", place_id, attempt + 1, e)
    return {}


# ---------------------------------------------------------------------------
# Backend detail fetch
# ---------------------------------------------------------------------------


async def be_get_place_details(
    client: httpx.AsyncClient,
    place_ids: list[str],
    user_location: dict[str, float] | None = None,
    transport_mode: str = "walking",
) -> str:
    if not place_ids:
        return ""

    params = {"ids": ",".join(place_ids), "forLLM": "true"}
    headers: dict[str, str] = {}
    if settings.be_bearer_token:
        headers["X-Internal-Authorization"] = f"Bearer {settings.be_bearer_token}"

    base = settings.be_base_url
    url = f"{base}/api/places/"

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            place_details = resp.json() or []

            if isinstance(place_details, dict):
                place_details = (
                    place_details.get("data")
                    or place_details.get("places")
                    or place_details.get("results")
                    or []
                )
            if not isinstance(place_details, list):
                logger.warning("Unexpected payload type from BE: %s", type(place_details))
                return ""

            for p in place_details:
                if not isinstance(p, dict):
                    continue
                pid = p.get("id")
                if not pid:
                    continue
                photos = p.get("photos") or []
                image_urls = [
                    ph.get("photoUri") for ph in photos if isinstance(ph, dict) and ph.get("photoUri")
                ]
                LAST_DETAIL_CACHE[pid] = {
                    "googleId": pid,
                    "address": p.get("shortFormattedAddress") or p.get("formattedAddress"),
                    "summary": p.get("summary"),
                    "imageUrls": image_urls,
                }

            blocks: list[str] = []
            for p in place_details:
                if not isinstance(p, dict):
                    continue
                name = p.get("name", "N/A")
                lat = p.get("latitude")
                lon = p.get("longitude")
                photos = p.get("photos", [])
                if not isinstance(photos, list):
                    photos = []
                image_urls = [ph.get("photoUri") for ph in photos if ph and ph.get("photoUri")]
                image_url = image_urls[0] if image_urls else None
                rating = p.get("rating", "N/A")
                types = ", ".join(p.get("types", []) or [])
                summary = p.get("summary", "N/A")
                address = p.get("shortFormattedAddress") or p.get("formattedAddress") or "N/A"
                pid = p.get("id", "N/A")
                open_now = p.get("openNow")
                open_until = p.get("openUntil")
                next_open = p.get("nextOpenTime")
                review_cnt = p.get("userRatingCount", p.get("reviewCount"))
                price_lvl = p.get("priceLevel")

                dist_km = None
                eta_min = None
                if user_location and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    dist_km = round(
                        haversine_km(user_location["latitude"], user_location["longitude"], lat, lon), 2
                    )
                    eta_min = eta_minutes(dist_km, transport_mode)

                block = (
                    f"| Name: {name} |\n"
                    f"| Latitude: {lat} |\n"
                    f"| Longitude: {lon} |\n"
                    f"| Address: {address} |\n"
                    f"| ImageUrl: {image_url} |\n"
                    f"| ImageUrls: {json.dumps(image_urls)} |\n"
                    f"| Rating: {rating} |\n"
                    f"| ReviewCount: {review_cnt} |\n"
                    f"| PriceLevel: {price_lvl} |\n"
                    f"| OpenNow: {open_now} |\n"
                    f"| OpenUntil: {open_until} |\n"
                    f"| NextOpenTime: {next_open} |\n"
                    f"| DistanceKmFromUser: {dist_km} |\n"
                    f"| ETA_Minutes_{transport_mode}: {eta_min} |\n"
                    f"| Types: {types} |\n"
                    f"| Summary: {summary} |\n"
                    f"| GoogleId: {pid} |\n"
                    f"| id: {pid} |\n"
                )
                blocks.append(block)
            return "\n".join(blocks) if blocks else ""

        except httpx.HTTPError as e:
            logger.warning("be_get_place_details attempt %d failed: %s", attempt + 1, e)
    return ""


def format_place_for_llm_from_google(p: dict) -> str:
    if not isinstance(p, dict):
        return ""

    name = (p.get("displayName") or {}).get("text", "N/A")
    loc = p.get("location") or {}
    lat, lon = loc.get("latitude", "N/A"), loc.get("longitude", "N/A")
    rating = p.get("rating", "N/A")
    review_count = p.get("userRatingCount", "N/A")
    price_level = (
        (p.get("priceLevel") or "").replace("PRICE_LEVEL_", "").replace("_", " ").title() or "N/A"
    )
    types = ", ".join(p.get("types", []) or [])
    pid = p.get("id", "N/A")
    address = p.get("shortFormattedAddress", "N/A")
    editorial = p.get("editorialSummary") or {}
    summary = editorial.get("overview", "N/A") if isinstance(editorial, dict) else "N/A"
    photos = p.get("photos", []) or []
    if not isinstance(photos, list):
        photos = []
    image_urls = [_photo_media_url(ph["name"]) for ph in photos if ph and ph.get("name")]
    image_url = image_urls[0] if image_urls else None
    coh = p.get("currentOpeningHours") or {}
    open_now = coh.get("openNow") if isinstance(coh, dict) else None

    return (
        f"| Name: {name} |\n"
        f"| Latitude: {lat} |\n"
        f"| Longitude: {lon} |\n"
        f"| Address: {address} |\n"
        f"| ImageUrl: {image_url} |\n"
        f"| ImageUrls: {json.dumps(image_urls)} |\n"
        f"| Rating: {rating} |\n"
        f"| ReviewCount: {review_count} |\n"
        f"| PriceLevel: {price_level} |\n"
        f"| OpenNow: {open_now} |\n"
        f"| Types: {types} |\n"
        f"| Summary: {summary} |\n"
        f"| GoogleId: {pid} |\n"
        f"| id: {pid} |\n"
    )


# ---------------------------------------------------------------------------
# High-level gathering functions
# ---------------------------------------------------------------------------


async def gather_instant_places(
    client: httpx.AsyncClient,
    instant_id: int,
    location: dict[str, Any],
) -> str:
    latitude = location.get("latitude", 22.281)
    longitude = location.get("longitude", 114.157)
    radius = 500

    queries = INSTANT_SEARCH_QUERIES.get(instant_id)
    if not queries:
        logger.error("Invalid instantId: %d", instant_id)
        return ""

    ids: list[str] = []
    for q in queries:
        ids += await google_text_search(client, q, latitude, longitude, radius, page_size=6)
    ids = _dedupe(ids)

    transport_mode = location.get("transportMode", "walking")
    place_details = await be_get_place_details(
        client, ids, user_location={"latitude": latitude, "longitude": longitude},
        transport_mode=transport_mode,
    )
    if place_details:
        return place_details

    # Fallback: fetch directly from Google
    logger.warning("BE failed for instant places, falling back to Google Details")
    formatted: list[str] = []
    for pid in ids[:20]:
        p = await google_place_details(client, pid)
        if p:
            formatted.append(format_place_for_llm_from_google(p))
    return "\n".join(formatted) if formatted else ""


async def gather_trip_places(
    client: httpx.AsyncClient,
    regions: list[str],
    categories: list[str],
    trip_length: int,
) -> list[str]:
    results: list[str] = []
    selected = list(categories or [])
    if "General" not in selected:
        selected.append("General")

    for area in regions or []:
        loc = LOCATION_DATA.get(area)
        if not loc:
            logger.warning("Unknown area: %s", area)
            continue
        lat = loc["latitude"]
        lon = loc["longitude"]
        rad = loc["radius"]

        for category in selected:
            query = TEXT_QUERY_DICT.get(category)
            if not query:
                logger.warning("Unknown category: %s", category)
                continue

            if category == "Outdoor Adventures" and isinstance(query, list):
                for q in query:
                    ids = await google_text_search(client, q, lat, lon, rad, page_size=7)
                    ids = _dedupe(ids)
                    if ids:
                        detail = await be_get_place_details(client, ids)
                        if detail:
                            results.append(detail)
            else:
                page_size = 20 if category == "General" else 15
                q = query if isinstance(query, str) else query[0]
                ids = await google_text_search(client, q, lat, lon, rad, page_size=page_size)
                ids = _dedupe(ids)
                if ids:
                    detail = await be_get_place_details(client, ids)
                    if detail:
                        results.append(detail)
    return results


# ---------------------------------------------------------------------------
# Cache hydration
# ---------------------------------------------------------------------------


async def hydrate_with_cache(client: httpx.AsyncClient, raw_json: str) -> str:
    try:
        data = json.loads(raw_json)
    except Exception:
        return raw_json

    results = data.get("results") or []
    changed = False

    for r in results:
        gid = r.get("googleId") or r.get("id")
        if not gid:
            continue

        detail = LAST_DETAIL_CACHE.get(gid) or {}
        addr = detail.get("address")
        summ = detail.get("summary")
        imgs = detail.get("imageUrls") or []

        if not addr or not summ or not imgs:
            p = await google_place_details(client, gid)
            if p:
                editorial = p.get("editorialSummary") or {}
                if not summ:
                    summ = editorial.get("overview", "") if isinstance(editorial, dict) else ""
                photos = p.get("photos") or []
                if not imgs and isinstance(photos, list):
                    imgs = [
                        _photo_media_url(ph["name"])
                        for ph in photos
                        if isinstance(ph, dict) and ph.get("name")
                    ]
                if not addr:
                    addr = p.get("shortFormattedAddress") or p.get("formattedAddress") or ""

        if gid:
            r["googleId"] = gid
        if addr and not r.get("address"):
            r["address"] = addr
        if summ and not r.get("summary"):
            r["summary"] = summ
        if imgs and not r.get("imageUrls"):
            r["imageUrls"] = imgs
        if not r.get("imageUrl") and imgs:
            r["imageUrl"] = imgs[0]
        changed = True

    return json.dumps(data, ensure_ascii=False) if changed else raw_json

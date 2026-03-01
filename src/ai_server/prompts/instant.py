"""Prompt templates and theme configs for instant recommendations."""

from __future__ import annotations

THEME_CONFIGS: dict[int, dict] = {
    1: {
        "title": "Chilling After Work",
        "rule": "Ensure at least one restaurant and one bar if available. Prioritize places open in evening hours.",
        "categories": ["restaurant", "bar", "lounge", "cafe"],
    },
    2: {
        "title": "Dating in Hong Kong",
        "rule": "Include romantic spots like cafes, scenic viewpoints, or parks. End with a romantic location if possible.",
        "categories": ["restaurant", "cafe", "park", "viewpoint", "romantic"],
    },
    3: {
        "title": "Explore art and culture in Hong Kong",
        "rule": "Prioritize museums, galleries, theaters, and cultural sites. Consider opening hours for cultural venues.",
        "categories": ["museum", "gallery", "theater", "cultural_site", "art"],
    },
    4: {
        "title": "Explore food and drink in Hong Kong",
        "rule": "Focus on diverse dining experiences - restaurants, cafes, dessert places, or food markets.",
        "categories": ["restaurant", "cafe", "dessert", "food_market", "bakery"],
    },
    5: {
        "title": "Nature Escapes",
        "rule": "Select parks, hiking trails, beaches, or botanical gardens. Consider weather and daylight hours.",
        "categories": ["park", "hiking", "beach", "garden", "nature"],
    },
    6: {
        "title": "Fitness & Wellness",
        "rule": "Include fitness facilities, spas, yoga studios, or wellness centers. Mix active and relaxing options.",
        "categories": ["gym", "spa", "yoga", "wellness", "fitness"],
    },
    7: {
        "title": "Shopping Spree",
        "rule": "Cover different shopping experiences - malls, boutiques, markets, or outlets.",
        "categories": ["mall", "boutique", "market", "outlet", "shopping"],
    },
    8: {
        "title": "Nightlife",
        "rule": "Focus on evening venues - bars, clubs, lounges, or live music venues. Consider operating hours.",
        "categories": ["bar", "club", "lounge", "live_music", "nightlife"],
    },
    9: {
        "title": "Kid-Friendly Fun",
        "rule": "Prioritize family-friendly venues - playgrounds, kid museums, amusement areas, or interactive spaces.",
        "categories": ["playground", "kids_museum", "amusement", "family", "interactive"],
    },
    10: {
        "title": "Pet-Friendly Fun",
        "rule": "Select pet-friendly cafes, parks, or pet stores. Ensure outdoor spaces are available.",
        "categories": ["pet_cafe", "dog_park", "pet_store", "outdoor", "pet_friendly"],
    },
    11: {
        "title": "Budget-Friendly Fun",
        "rule": "Focus on free or low-cost attractions - public parks, free museums, affordable food spots.",
        "categories": ["free_attraction", "public_park", "affordable_food", "budget", "free"],
    },
    12: {
        "title": "Seasonal (Festivals, etc.)",
        "rule": "Prioritize seasonal events, holiday markets, or festival locations. Consider current season.",
        "categories": ["festival", "seasonal_event", "holiday_market", "celebration", "seasonal"],
    },
    13: {
        "title": "Relax & Recharge",
        "rule": "Select calming venues - spas, tea houses, quiet cafes, or meditation centers.",
        "categories": ["spa", "tea_house", "quiet_cafe", "meditation", "relaxation"],
    },
    14: {
        "title": "Adventure Mode",
        "rule": "Focus on thrilling activities - water sports, extreme sports, adventure parks, or outdoor challenges.",
        "categories": ["water_sports", "extreme_sports", "adventure_park", "outdoor_challenge", "thrill"],
    },
}

_DEFAULT_THEME = {
    "title": "General Exploration",
    "rule": "Select diverse and interesting places based on proximity and quality.",
    "categories": ["general"],
}


def build_instant_prompt(
    instant_id: int,
    location: dict,
    places_str: str,
    *,
    k: int = 5,
    transport_mode: str = "walking",
    max_distance_km: float = 2.0,
    now_local: str = "auto",
    output_language: str = "en",
) -> str:
    cfg = THEME_CONFIGS.get(instant_id, _DEFAULT_THEME)
    title = cfg["title"]
    rule = cfg["rule"]
    cats = ", ".join(cfg["categories"])

    return f"""SYSTEM
You are an expert Hong Kong after-work concierge. Provide practical, safe, now-reachable recommendations near the user.
Do necessary calculations internally, but output ONLY the final JSON—no chain-of-thought.

USER
Destination candidates (choose ONLY from this list; DO NOT invent new places):
{places_str}

Context:
- Theme: "{title}"
- User location (lat, lng): {location}
- Current local datetime (Asia/Hong_Kong): {now_local}
- Transport mode: {transport_mode}
- Max results: {k}
- Max radius (km): {max_distance_km}
- Output language: {output_language}
- Theme categories: {cats}

Hard rules:
1) Use ONLY the given candidates and their exact ids.
2) Prioritize proximity & ETA first, then open status, then quality (rating & review_count).
3) Prefer places open now; "opens_soon" if opens within 60 minutes; "closing_soon" if closes within 45 minutes.
4) {rule}
5) De-duplicate near-identical entries.
6) Stay within {max_distance_km} km unless necessary; note expansions in coverage.notes.
7) Output JSON ONLY (schema below). No extra text.

Selection scoring:
A) Distance & ETA (Haversine vs. user location; walking~4.8km/h, transit~12km/h, driving~25km/h)
B) Open status (open > opens_soon > unknown > closing_soon > closed)
C) Quality (rating, review_count), then price_level
D) Theme fit ({cats})

Output JSON:
{{
  "theme": "{title}",
  "now_local": "{now_local}",
  "transport_mode": "{transport_mode}",
  "results": [
    {{
      "id": "<id>",
      "name": "<name>",
      "category": "<category>",
      "latitude": <number>,
      "longitude": <number>,
      "imageUrl": "<url or null>",
      "distance_km": <number>,
      "eta_minutes": <int>,
      "open_status": "open" | "closing_soon" | "opens_soon" | "closed" | "unknown",
      "open_until": "<HH:mm or null>",
      "next_open_time": "<HH:mm or null>",
      "rating": <number or null>,
      "review_count": <int or null>,
      "price_level": "$" | "$$" | "$$$" | null,
      "reasons": ["<short bullet>", "..."]
    }}
  ],
  "coverage": {{
    "requested_results": {k},
    "returned_results": <int>,
    "theme_coverage": "<description of how well theme requirements were met>",
    "notes": "<text>"
  }}
}}"""

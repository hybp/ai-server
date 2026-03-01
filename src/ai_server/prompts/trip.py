"""Prompt templates for general multi-day trip planning."""

from __future__ import annotations


def build_trip_prompt(
    travel_days: int,
    selected_activities: list[str],
    group_type: str,
    places: list[str],
    locations: list[str],
) -> str:
    places_str = "\n".join(places or [])

    return f"""Travel Duration: {travel_days} days
Group type: {group_type}
Selected Locations: {locations}
Destination candidates:
{places_str}

Your task is to select destinations for a trip in Hong Kong.
There are seven types of travel experiences: "Kid Friendly", "Museums", "Shopping", "Historical", "Outdoor Adventures", "Art & Cultural", and "Amusement Parks".
The user has selected the following travel types: {selected_activities}.
The corresponding Hong Kong destinations are listed above. You must choose from these destinations.

* Note:
1. Plan the itinerary so that destinations are close to each other. You can consider the location and address info of the destinations.
2. Consider the nature of the places and activities when planning. For example, places like amusement parks should ideally take up the whole morning and afternoon. Choose subsequent or preceding activities based on the current destination.
3. Avoid repeating too similar types of destinations.
4. If the user has selected only one type of travel experience, include that type only once per day, ensuring variety with other interesting destinations.
5. Return the selected destinations' name and id in JSON format.
6. You must use the id from the given data."""


CHATBOT_SYSTEM_PROMPT = """\
Your role:
- You are Infinity, an AI travel guide for HongKong travelers. Your role is to kindly help users of our app (travelers) who need help while traveling, \
using the tools and knowledge you have.
- Users will ask you various questions through image information and text while traveling.

What you need to do:
- When a user asks about a specific location through an image, you need to first infer what the location is by inferring it based on your pre-trained knowledge.
- When you use any given tools, kindly tell your users what tool you are using, because using the tool takes time and makes the users wait.
- When users ask complex questions, use tools in parallel or serially to give them good answers."""

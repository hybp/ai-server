"""LangGraph workflow for multi-day trip planning."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, TypedDict

import httpx
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, StateGraph

from ai_server.config import settings
from ai_server.models.trip import TripPlan
from ai_server.prompts.trip import build_trip_prompt
from ai_server.services.places import gather_trip_places

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 2


class TripState(TypedDict, total=False):
    start_date: str
    end_date: str
    regions: list[str]
    categories: list[str]
    group_type: str
    travel_days: int
    places: list[str]
    prompt: str
    raw_llm_output: dict | None
    result_json: str
    retries: int
    error: str | None


def _create_llm():
    if settings.deepseek_api_key:
        try:
            from langchain_deepseek import ChatDeepSeek

            os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key
            return ChatDeepSeek(model="deepseek-chat", temperature=0, streaming=False)
        except Exception:
            logger.warning("DeepSeek unavailable, falling back to OpenAI")

    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model="gpt-4o-mini-2024-07-18", temperature=0, streaming=False)


def _transform_trip_plan(trip_plan: TripPlan) -> str:
    output = {
        str(dp.day): [p.model_dump() for p in dp.destinations]
        for dp in trip_plan.days
    }
    return json.dumps(output, ensure_ascii=False, indent=4)


async def compute_days_node(state: TripState) -> dict:
    try:
        sd = datetime.strptime(state["start_date"], "%Y-%m-%d").date()
        ed = datetime.strptime(state["end_date"], "%Y-%m-%d").date()
        travel_days = (ed - sd).days + 1
        if travel_days < 1:
            return {"error": "End date must be after start date"}
        return {"travel_days": travel_days}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}


async def gather_places_node(state: TripState) -> dict:
    async with httpx.AsyncClient() as client:
        places = await gather_trip_places(
            client,
            state.get("regions") or ["Hong Kong"],
            state.get("categories") or [],
            state["travel_days"],
        )
    if not places:
        return {"error": "No candidate places gathered for trip"}
    return {"places": places}


async def build_prompt_node(state: TripState) -> dict:
    prompt = build_trip_prompt(
        state["travel_days"],
        state.get("categories") or [],
        state.get("group_type", ""),
        state["places"],
        state.get("regions") or ["Hong Kong"],
    )
    return {"prompt": prompt}


async def call_llm_node(state: TripState) -> dict:
    llm = _create_llm()
    parser = JsonOutputParser(pydantic_object=TripPlan)
    prompt_tpl = PromptTemplate(
        template="{format_instructions}\n{query}\n",
        input_variables=["query"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    chain = prompt_tpl | llm | parser
    result = await chain.ainvoke({"query": state["prompt"]})
    return {"raw_llm_output": result}


async def parse_and_validate_node(state: TripState) -> dict:
    raw = state.get("raw_llm_output")
    retries = state.get("retries", 0)
    try:
        parsed = TripPlan.model_validate(raw)
        return {"result_json": _transform_trip_plan(parsed)}
    except Exception as e:
        if retries < MAX_LLM_RETRIES:
            logger.warning("Trip parsing failed (attempt %d), retrying: %s", retries + 1, e)
            return {"retries": retries + 1, "raw_llm_output": None}
        return {"error": f"Failed to parse trip plan after {retries + 1} attempts: {e}"}


def should_retry(state: TripState) -> str:
    if state.get("error"):
        return "end"
    if state.get("result_json"):
        return "done"
    return "retry"


def build_trip_graph() -> StateGraph:
    g = StateGraph(TripState)

    g.add_node("compute_days", compute_days_node)
    g.add_node("gather_places", gather_places_node)
    g.add_node("build_prompt", build_prompt_node)
    g.add_node("call_llm", call_llm_node)
    g.add_node("parse_and_validate", parse_and_validate_node)

    g.set_entry_point("compute_days")

    g.add_conditional_edges(
        "compute_days",
        lambda s: "end" if s.get("error") else "continue",
        {"end": END, "continue": "gather_places"},
    )
    g.add_conditional_edges(
        "gather_places",
        lambda s: "end" if s.get("error") else "continue",
        {"end": END, "continue": "build_prompt"},
    )
    g.add_edge("build_prompt", "call_llm")
    g.add_edge("call_llm", "parse_and_validate")
    g.add_conditional_edges(
        "parse_and_validate",
        should_retry,
        {"retry": "call_llm", "done": END, "end": END},
    )

    return g


trip_graph = build_trip_graph().compile()

"""LangGraph workflow for instant theme-based recommendations."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, TypedDict

import httpx
import pytz
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, StateGraph

from ai_server.config import settings
from ai_server.models.instant import InstantRecommendations
from ai_server.prompts.instant import build_instant_prompt
from ai_server.services.places import gather_instant_places, hydrate_with_cache

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 2


class InstantState(TypedDict, total=False):
    instant_id: int
    location: dict[str, Any]
    k: int
    transport_mode: str
    max_distance_km: float
    now_local: str | None
    language: str
    places_str: str
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


async def gather_places_node(state: InstantState) -> dict:
    async with httpx.AsyncClient() as client:
        places_str = await gather_instant_places(
            client, state["instant_id"], state.get("location") or {}
        )
    if not places_str:
        return {"error": "No candidate places found for instant recommendation"}
    return {"places_str": places_str}


async def build_prompt_node(state: InstantState) -> dict:
    now = state.get("now_local")
    if not now:
        hk_tz = pytz.timezone("Asia/Hong_Kong")
        now = datetime.now(hk_tz).strftime("%Y-%m-%d %H:%M")

    prompt = build_instant_prompt(
        state["instant_id"],
        state.get("location") or {},
        state["places_str"],
        k=state.get("k", 5),
        transport_mode=state.get("transport_mode", "walking"),
        max_distance_km=state.get("max_distance_km", 2.0),
        now_local=now,
        output_language=state.get("language", "en"),
    )
    return {"prompt": prompt, "now_local": now}


async def call_llm_node(state: InstantState) -> dict:
    llm = _create_llm()
    parser = JsonOutputParser(pydantic_object=InstantRecommendations)
    prompt_tpl = PromptTemplate(
        template="{format_instructions}\n{query}\n",
        input_variables=["query"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    chain = prompt_tpl | llm | parser
    result = await chain.ainvoke({"query": state["prompt"]})
    return {"raw_llm_output": result}


async def parse_and_validate_node(state: InstantState) -> dict:
    raw = state.get("raw_llm_output")
    retries = state.get("retries", 0)
    try:
        parsed = InstantRecommendations.model_validate(raw)
        return {"result_json": parsed.model_dump_json(by_alias=True)}
    except Exception as e:
        if retries < MAX_LLM_RETRIES:
            logger.warning("Parsing failed (attempt %d), retrying: %s", retries + 1, e)
            return {"retries": retries + 1, "raw_llm_output": None}
        return {"error": f"Failed to parse LLM output after {retries + 1} attempts: {e}"}


def should_retry(state: InstantState) -> str:
    if state.get("error"):
        return "end"
    if state.get("result_json"):
        return "hydrate"
    return "retry"


async def hydrate_node(state: InstantState) -> dict:
    async with httpx.AsyncClient() as client:
        hydrated = await hydrate_with_cache(client, state["result_json"])
    return {"result_json": hydrated}


def build_instant_graph() -> StateGraph:
    g = StateGraph(InstantState)

    g.add_node("gather_places", gather_places_node)
    g.add_node("build_prompt", build_prompt_node)
    g.add_node("call_llm", call_llm_node)
    g.add_node("parse_and_validate", parse_and_validate_node)
    g.add_node("hydrate", hydrate_node)

    g.set_entry_point("gather_places")

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
        {"retry": "call_llm", "hydrate": "hydrate", "end": END},
    )
    g.add_edge("hydrate", END)

    return g


instant_graph = build_instant_graph().compile()

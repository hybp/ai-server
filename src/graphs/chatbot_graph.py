"""LangGraph workflow for the travel chatbot."""

from __future__ import annotations

import logging
import os
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from config import settings
from prompts.trip import CHATBOT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ChatState(TypedDict, total=False):
    user_id: int
    message: str
    image_base64: str | None
    history: list[dict]
    reply: str
    error: str | None


def _create_llm():
    if settings.deepseek_api_key:
        try:
            from langchain_deepseek import ChatDeepSeek

            os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key
            return ChatDeepSeek(model="deepseek-chat", temperature=0.7, streaming=False)
        except Exception:
            logger.warning("DeepSeek unavailable, falling back to OpenAI")

    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model="gpt-4o-mini-2024-07-18", temperature=0.7, streaming=False)


async def build_messages_node(state: ChatState) -> dict:
    messages: list = [SystemMessage(content=CHATBOT_SYSTEM_PROMPT)]

    for h in state.get("history") or []:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    user_content: list = []
    user_content.append({"type": "text", "text": state["message"]})

    img = state.get("image_base64")
    if img:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img}"},
        })

    messages.append(HumanMessage(content=user_content))
    return {"_messages": messages}


async def call_llm_node(state: ChatState) -> dict:
    # _messages is passed via state dict (transient key)
    messages = state.get("_messages")  # type: ignore[typeddict-item]
    if not messages:
        return {"error": "No messages built"}

    llm = _create_llm()
    try:
        response = await llm.ainvoke(messages)
        return {"reply": response.content}
    except Exception as e:
        logger.error("Chatbot LLM call failed: %s", e)
        return {"error": str(e)}


def build_chatbot_graph() -> StateGraph:
    g = StateGraph(ChatState)

    g.add_node("build_messages", build_messages_node)
    g.add_node("call_llm", call_llm_node)

    g.set_entry_point("build_messages")
    g.add_edge("build_messages", "call_llm")
    g.add_edge("call_llm", END)

    return g


chatbot_graph = build_chatbot_graph().compile()

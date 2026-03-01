"""RabbitMQ consumer: listens on ai.task queue, routes by taskType, replies."""

from __future__ import annotations

import json
import logging
import traceback

import aio_pika
from aio_pika import Message
from aio_pika.abc import AbstractIncomingMessage

from ai_server.config import settings
from ai_server.graphs.chatbot_graph import chatbot_graph
from ai_server.graphs.instant_graph import instant_graph
from ai_server.graphs.trip_graph import trip_graph

logger = logging.getLogger(__name__)


async def _handle_trip_plan(payload: dict) -> str:
    state = {
        "start_date": payload.get("startDate", ""),
        "end_date": payload.get("endDate", ""),
        "regions": payload.get("regions", ["Hong Kong"]),
        "categories": payload.get("categories", []),
        "group_type": payload.get("groupType", ""),
    }
    result = await trip_graph.ainvoke(state)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result["result_json"]


async def _handle_instant(payload: dict) -> str:
    state = {
        "instant_id": payload.get("instantId", 0),
        "location": payload.get("location"),
        "k": payload.get("k", 5),
        "transport_mode": payload.get("transportMode", "walking"),
        "max_distance_km": payload.get("maxDistanceKm", 2.0),
        "now_local": payload.get("nowLocal"),
        "language": payload.get("language", "en"),
    }
    result = await instant_graph.ainvoke(state)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result["result_json"]


async def _handle_chatbot(payload: dict) -> str:
    state = {
        "user_id": payload.get("userId", 0),
        "message": payload.get("message", ""),
        "image_base64": payload.get("imageBase64"),
        "history": payload.get("history", []),
    }
    result = await chatbot_graph.ainvoke(state)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return json.dumps({"reply": result["reply"]}, ensure_ascii=False)


_HANDLERS = {
    "TRIP_PLAN": _handle_trip_plan,
    "INSTANT_RECOMMENDATION": _handle_instant,
    "CHATBOT": _handle_chatbot,
}


async def on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        body = json.loads(message.body.decode())
        task_type = body.get("taskType", "")
        correlation_id = body.get("correlationId", message.correlation_id or "")
        payload = body.get("payload")

        if isinstance(payload, str):
            payload = json.loads(payload)

        logger.info("Received task: type=%s corr=%s", task_type, correlation_id)

        handler = _HANDLERS.get(task_type)
        if not handler:
            result_body = _error_reply(correlation_id, f"Unknown taskType: {task_type}")
        else:
            try:
                result_payload = await handler(payload)
                result_body = json.dumps({
                    "correlationId": correlation_id,
                    "success": True,
                    "payload": result_payload,
                    "error": None,
                }, ensure_ascii=False)
            except Exception as e:
                logger.error("Task %s failed: %s\n%s", task_type, e, traceback.format_exc())
                result_body = _error_reply(correlation_id, str(e))

        if message.reply_to:
            channel = message.channel
            await channel.default_exchange.publish(
                Message(
                    body=result_body.encode(),
                    correlation_id=message.correlation_id,
                    content_type="application/json",
                ),
                routing_key=message.reply_to,
            )
            logger.info("Replied to %s for corr=%s", message.reply_to, correlation_id)


def _error_reply(correlation_id: str, error: str) -> str:
    return json.dumps({
        "correlationId": correlation_id,
        "success": False,
        "payload": None,
        "error": error,
    }, ensure_ascii=False)


async def start_consumer(connection: aio_pika.abc.AbstractRobustConnection) -> None:
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    queue = await channel.declare_queue(settings.task_queue, durable=True)
    await queue.consume(on_message)
    logger.info("Consuming from queue '%s'", settings.task_queue)

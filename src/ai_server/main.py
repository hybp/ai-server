"""FastAPI application entry point with RabbitMQ lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI

from ai_server.config import settings
from ai_server.consumer import start_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to RabbitMQ at %s", settings.rabbitmq_url)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    app.state.rmq_connection = connection
    await start_consumer(connection)
    logger.info("AI server ready")
    yield
    await connection.close()
    logger.info("RabbitMQ connection closed")


app = FastAPI(
    title="Trippy AI Server",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}

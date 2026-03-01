from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    user_id: int = Field(alias="userId")
    message: str
    image_base64: str | None = Field(default=None, alias="imageBase64")
    history: list[ChatMessage] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ChatResponse(BaseModel):
    reply: str

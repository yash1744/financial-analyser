"""LLM chat endpoints: one-shot and Server-Sent-Events streaming."""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.ai.exceptions import AIError
from app.ai.schemas import AgentEvent, ChatRequest, ChatResponse
from app.api.deps import ChatServiceDep
from app.services.exceptions import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    """One-shot chat: runs the full tool loop and returns the final answer."""
    return await service.chat(body)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _event_name(event: AgentEvent) -> str:
    return event.type  # "token" | "tool" | "done"


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, service: ChatServiceDep) -> StreamingResponse:
    """SSE stream of the same loop: `token` events (assistant text),
    `tool` events (running/completed/failed), one final `done` event.
    Errors after the stream opens arrive as an `error` event."""

    async def generate():
        try:
            async for event in service.chat_stream(body):
                payload = event.model_dump(mode="json", exclude={"type"})
                yield _sse(_event_name(event), payload)
        except (AIError, NotFoundError) as exc:
            # the SSE stream is already open (200), so errors ride the stream
            yield _sse("error", {"detail": str(exc)})
        except Exception:
            logger.exception("chat stream failed")
            yield _sse("error", {"detail": "internal error"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

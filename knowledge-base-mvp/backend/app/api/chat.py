"""
Chat & retrieval API routes.
POST /api/v1/chat — stream RAG response via Server-Sent Events.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    organization_id: str
    question: str
    stream: bool = True
    top_k: int = 5


@router.post("")
async def chat(request: ChatRequest):
    """
    Submit a question and receive a streamed RAG response.
    
    The response uses Server-Sent Events (SSE) format:
    - Token events: data: {"token": "partial text"}\n\n
    - Final sources: data: {"sources": [...]}\n\n
    - End signal:    data: [DONE]\n\n
    """
    from app.main import chat_service

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if not request.organization_id.strip():
        raise HTTPException(status_code=400, detail="Organization ID is required")

    return StreamingResponse(
        chat_service.stream_response(
            organization_id=request.organization_id,
            question=request.question,
            top_k=request.top_k,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

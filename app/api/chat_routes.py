from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.service.chat_service import answer_chat

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return answer_chat(request)

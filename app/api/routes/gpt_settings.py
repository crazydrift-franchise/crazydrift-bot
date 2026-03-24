from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.api.routes.auth import verify_token
from app.repositories.faq_repo import GptSettingsRepository
from app.repositories.faq_repo import KnowledgeRepository
from app.services.ai.claude_service import ask_bot

router = APIRouter()


class GptSettingsUpdate(BaseModel):
    system_prompt: str = ""
    analysis_prompt: str = ""
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 1000


class TestPromptRequest(BaseModel):
    message: str


@router.get("/")
async def get_settings(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = GptSettingsRepository(db)
    s = await repo.get_or_create()
    return {
        "id": s.id,
        "system_prompt": s.system_prompt,
        "analysis_prompt": s.analysis_prompt,
        "model": s.model,
        "temperature": s.temperature,
        "max_tokens": s.max_tokens,
    }


@router.patch("/")
async def update_settings(
    body: GptSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    repo = GptSettingsRepository(db)
    s = await repo.get_or_create()
    s.system_prompt = body.system_prompt
    s.analysis_prompt = body.analysis_prompt
    s.model = body.model
    s.temperature = body.temperature
    s.max_tokens = body.max_tokens
    return {"ok": True}


@router.post("/test")
async def test_prompt(
    body: TestPromptRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    repo = GptSettingsRepository(db)
    kb_repo = KnowledgeRepository(db)
    s = await repo.get_or_create()
    knowledge = await kb_repo.get_as_text()
    answer = await ask_bot(body.message, s.system_prompt, knowledge)
    return {"answer": answer}

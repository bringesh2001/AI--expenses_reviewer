"""Policy Q&A — hybrid retrieval + scope gate + Claude reasoning."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database import get_db
from ..auth import get_current_user_id
from ..services.qa import answer_question

router = APIRouter(prefix="/qa", tags=["qa"])


class QARequest(BaseModel):
    question: str


class QAResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: str | None
    status: str
    citations: list | None
    confidence: float | None

    model_config = {"from_attributes": True}


@router.post("/", response_model=QAResponse)
async def ask(
    body: QARequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    session = await answer_question(
        question=body.question.strip(),
        user_id=user_id,
        db=db,
    )
    return session

"""Submissions router — create, upload receipts, poll status, list, review actions."""
import uuid
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database import get_db
from ..models.submission import Submission, SubmissionStatus
from ..models.line_item import LineItem
from ..models.employee import Employee
from ..models.audit_log import AuditLog, AuditAction, ActorType
from ..auth import get_current_user_id

router = APIRouter(prefix="/submissions", tags=["submissions"])


# ── Pydantic response schemas ─────────────────────────────────────────────────


class LineItemOut(BaseModel):
    id: uuid.UUID
    receipt_filename: Optional[str] = None
    category: Optional[str] = None
    vendor: Optional[str] = None
    transaction_date: Optional[date] = None
    amount: Optional[float] = None
    currency: str = "USD"
    payment_method: Optional[str] = None
    verdict: Optional[str] = None
    effective_verdict: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    citations: Optional[list] = None
    retrieval_score: Optional[float] = None
    override_verdict: Optional[str] = None
    override_note: Optional[str] = None

    model_config = {"from_attributes": True}


class SubmissionOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    trip_purpose: str
    trip_destination: str
    trip_start_date: date
    trip_end_date: date
    status: str
    total_amount: Optional[float] = None
    snapshot_grade: int
    snapshot_department: str
    reviewer_id: Optional[str] = None
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    line_items: list[LineItemOut] = []

    model_config = {"from_attributes": True}


class SubmissionCreate(BaseModel):
    employee_id: str
    trip_purpose: str
    trip_destination: str
    trip_start_date: date
    trip_end_date: date


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "send_back"
    note: Optional[str] = None


class OverrideRequest(BaseModel):
    verdict: str  # compliant | flagged | needs_review | rejected
    note: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_sub_with_items(submission_id: uuid.UUID, db: AsyncSession) -> Submission:
    result = await db.execute(
        select(Submission)
        .options(selectinload(Submission.line_items))
        .where(Submission.id == submission_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=SubmissionOut)
async def create_submission(
    body: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
):
    emp_result = await db.execute(select(Employee).where(func.upper(Employee.employee_id) == body.employee_id.upper()))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{body.employee_id}' not found")

    sub = Submission(
        id=uuid.uuid4(),
        employee_id=emp.id,
        trip_purpose=body.trip_purpose,
        trip_destination=body.trip_destination,
        trip_start_date=body.trip_start_date,
        trip_end_date=body.trip_end_date,
        status=SubmissionStatus.draft.value,
        snapshot_grade=emp.grade,
        snapshot_department=emp.department,
    )
    db.add(sub)
    db.add(AuditLog(
        id=uuid.uuid4(),
        submission_id=sub.id,
        action=AuditAction.created.value,
        actor_type=ActorType.system.value,
        new_value={"employee_id": body.employee_id, "destination": body.trip_destination},
    ))
    await db.commit()
    return await _get_sub_with_items(sub.id, db)


@router.post("/{submission_id}/receipts", status_code=status.HTTP_202_ACCEPTED)
async def upload_receipt(
    submission_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    sub = await _get_sub_with_items(submission_id, db)
    if sub.status not in (SubmissionStatus.draft.value, SubmissionStatus.needs_revision.value):
        raise HTTPException(status_code=409, detail=f"Submission is locked (status={sub.status})")

    content = await file.read()
    filename = file.filename or "receipt"

    item = LineItem(
        id=uuid.uuid4(),
        submission_id=submission_id,
        receipt_filename=filename,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Kick off extraction + verdict in background
    from ..services.pipeline import process_receipt
    background_tasks.add_task(
        process_receipt, item.id, filename, content, submission_id
    )

    return {"line_item_id": str(item.id), "status": "queued"}


@router.post("/{submission_id}/submit", response_model=SubmissionOut)
async def submit_for_review(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    sub = await _get_sub_with_items(submission_id, db)
    if sub.status != SubmissionStatus.draft.value:
        raise HTTPException(status_code=409, detail=f"Cannot submit from status '{sub.status}'")
    if not sub.line_items:
        raise HTTPException(status_code=422, detail="No receipts uploaded yet")

    sub.status = SubmissionStatus.pending_review.value
    await db.commit()
    return await _get_sub_with_items(submission_id, db)


@router.post("/{submission_id}/review", response_model=SubmissionOut)
async def review_submission(
    submission_id: uuid.UUID,
    body: ReviewAction,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, or send back a submission. Approved submissions become read-only."""
    sub = await _get_sub_with_items(submission_id, db)
    if sub.status not in (SubmissionStatus.pending_review.value,):
        raise HTTPException(status_code=409, detail=f"Cannot review from status '{sub.status}'")

    action_map = {
        "approve": (SubmissionStatus.approved.value, AuditAction.approved.value),
        "reject": (SubmissionStatus.rejected.value, AuditAction.rejected.value),
        "send_back": (SubmissionStatus.needs_revision.value, AuditAction.sent_back.value),
    }
    if body.action not in action_map:
        raise HTTPException(status_code=422, detail=f"Unknown action '{body.action}'")

    new_status, audit_action = action_map[body.action]
    sub.status = new_status
    sub.reviewer_id = user_id
    sub.reviewer_note = body.note
    sub.reviewed_at = datetime.utcnow()

    db.add(AuditLog(
        id=uuid.uuid4(),
        submission_id=submission_id,
        action=audit_action,
        actor_type=ActorType.reviewer.value,
        actor_id=user_id,
        note=body.note,
    ))
    await db.commit()
    return await _get_sub_with_items(submission_id, db)


@router.post("/{submission_id}/items/{item_id}/override", response_model=SubmissionOut)
async def override_verdict(
    submission_id: uuid.UUID,
    item_id: uuid.UUID,
    body: OverrideRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Override the AI verdict on a single line item. Append-only audit entry."""
    sub = await _get_sub_with_items(submission_id, db)
    if sub.status == SubmissionStatus.approved.value:
        raise HTTPException(status_code=409, detail="Approved submissions are read-only")

    item_result = await db.execute(
        select(LineItem).where(LineItem.id == item_id, LineItem.submission_id == submission_id)
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Line item not found")

    old_verdict = item.effective_verdict
    item.override_verdict = body.verdict
    item.override_note = body.note
    item.effective_verdict = body.verdict  # materialized for dashboard queries

    # Append-only override row
    db.add(AuditLog(
        id=uuid.uuid4(),
        submission_id=submission_id,
        line_item_id=item_id,
        action=AuditAction.reviewer_override.value,
        actor_type=ActorType.reviewer.value,
        actor_id=user_id,
        old_value={"verdict": old_verdict},
        new_value={"verdict": body.verdict},
        note=body.note,
    ))
    await db.commit()
    return await _get_sub_with_items(submission_id, db)


@router.get("/{submission_id}/audit", response_model=list[dict])
async def get_audit_log(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.submission_id == submission_id)
        .order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "action": log.action,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "note": log.note,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/{submission_id}", response_model=SubmissionOut)
async def get_submission(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get_sub_with_items(submission_id, db)


@router.get("/", response_model=list[SubmissionOut])
async def list_submissions(
    employee_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(Submission).options(selectinload(Submission.line_items))
    if employee_id:
        emp_result = await db.execute(select(Employee).where(func.upper(Employee.employee_id) == employee_id.upper()))
        emp = emp_result.scalar_one_or_none()
        if emp:
            q = q.where(Submission.employee_id == emp.id)
    if status_filter:
        q = q.where(Submission.status == status_filter)
    q = q.order_by(Submission.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()

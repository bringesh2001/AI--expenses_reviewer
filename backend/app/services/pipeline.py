"""
Submission pre-review pipeline orchestrator.

Pass 1: Per-item extraction + verdict (parallelised)
Pass 2: Cross-item rules
  - Duplicate detection (same vendor+date+amount → flag second occurrence)
  - Daily meal cap check (sum of meals per date vs per-diem cap)
  - Approval threshold (total → determines required approval level)
  - Overall submission status determination

Async: runs in a background task started by the submissions router.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models.submission import Submission, SubmissionStatus
from ..models.line_item import LineItem
from ..models.audit_log import AuditLog, AuditAction, ActorType
from .extraction import extract_receipt, ReceiptFields
from .verdict import compute_verdict

# Per-diem meal caps from TEP-002 / TEP-008 (simplified; Tier 1 cities get 25% uplift)
_TIER1_CITIES = {"new york", "san francisco", "los angeles", "boston", "washington"}
_MEAL_CAP_BASE = 75.0   # solo dinner Tier 2
_MEAL_CAP_TIER1 = 93.75 # 25% uplift
_DAILY_MEAL_CAP_BASE = 150.0
_DAILY_MEAL_CAP_TIER1 = 187.5

# Approval thresholds from TEP-001 §4
_APPROVAL_THRESHOLDS = [
    (1000.0, "self"),
    (5000.0, "manager"),
    (float("inf"), "director"),
]


def _city_tier1(city: str | None) -> bool:
    return bool(city and city.lower().strip() in _TIER1_CITIES)


def _required_approval(total: float) -> str:
    for limit, level in _APPROVAL_THRESHOLDS:
        if total <= limit:
            return level
    return "director"


async def run_pipeline(submission_id: uuid.UUID) -> None:
    """Entry point for background task."""
    async with AsyncSessionLocal() as db:
        await _run(submission_id, db)


async def _run(submission_id: uuid.UUID, db: AsyncSession) -> None:
    # Fetch submission + items
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    items_result = await db.execute(
        select(LineItem).where(LineItem.submission_id == submission_id)
    )
    items: list[LineItem] = list(items_result.scalars().all())

    if not items:
        sub.status = SubmissionStatus.needs_revision.value
        await db.commit()
        return

    # ── Pass 1: per-item extraction + verdict ─────────────────────────────────
    async def process_item(item: LineItem) -> None:
        if not item.receipt_filename:
            return
        # Retrieve stored file bytes from memory (content was passed at upload time)
        # In production, fetch from object storage; here we re-process from stored path
        # For scaffold: skip if no content available (will be wired in M6)
        pass

    # Run all items concurrently
    await asyncio.gather(*[process_item(item) for item in items])

    # ── Pass 2: cross-item rules ──────────────────────────────────────────────
    _check_duplicates(items)
    _check_daily_meal_caps(items, sub.trip_destination)

    # Compute total and determine approval level
    total = sum(
        float(item.amount or 0)
        for item in items
        if item.effective_verdict not in ("rejected",)
    )
    sub.total_amount = total

    approval_needed = _required_approval(total)

    # Write approval info to audit log
    db.add(AuditLog(
        id=uuid.uuid4(),
        submission_id=submission_id,
        action=AuditAction.ai_verdict.value,
        actor_type=ActorType.system.value,
        new_value={
            "total_amount": total,
            "approval_needed": approval_needed,
            "grade": sub.snapshot_grade,
        },
    ))

    # Determine overall submission status
    verdicts = [item.effective_verdict for item in items if item.effective_verdict]
    if any(v == "rejected" for v in verdicts):
        sub.status = SubmissionStatus.needs_revision.value
    elif any(v in ("flagged", "needs_review") for v in verdicts):
        sub.status = SubmissionStatus.pending_review.value
    else:
        sub.status = SubmissionStatus.pending_review.value

    await db.commit()


def _check_duplicates(items: list[LineItem]) -> None:
    seen: set[tuple] = set()
    for item in items:
        key = (item.vendor, item.transaction_date, item.amount)
        if None not in key and key in seen:
            item.effective_verdict = "flagged"
            item.reasoning = (
                (item.reasoning or "") +
                " [DUPLICATE FLAG: same vendor/date/amount appears multiple times]"
            )
        seen.add(key)


def _check_daily_meal_caps(items: list[LineItem], destination: str) -> None:
    """Group meal items by date; flag if total exceeds daily cap."""
    tier1 = _city_tier1(destination)
    daily_cap = _DAILY_MEAL_CAP_TIER1 if tier1 else _DAILY_MEAL_CAP_BASE

    by_date: dict[date, list[LineItem]] = {}
    for item in items:
        if item.category == "meal" and item.transaction_date and item.amount:
            by_date.setdefault(item.transaction_date, []).append(item)

    for dt, meal_items in by_date.items():
        daily_total = sum(float(i.amount or 0) for i in meal_items)
        if daily_total > daily_cap:
            for item in meal_items:
                if item.effective_verdict not in ("rejected",):
                    item.effective_verdict = "flagged"
                    item.reasoning = (
                        (item.reasoning or "") +
                        f" [DAILY CAP: meals on {dt} total ${daily_total:.2f}, cap ${daily_cap:.2f}]"
                    )


async def process_receipt(
    line_item_id: uuid.UUID,
    filename: str,
    content: bytes,
    submission_id: uuid.UUID,
) -> None:
    """
    Extract fields and compute verdict for a single line item.
    Called directly at upload time (M6 integration).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(LineItem).where(LineItem.id == line_item_id))
        item = result.scalar_one_or_none()
        if not item:
            return

        sub_result = await db.execute(select(Submission).where(Submission.id == submission_id))
        sub = sub_result.scalar_one_or_none()
        if not sub:
            return

        # Extract
        fields: ReceiptFields = await asyncio.to_thread(extract_receipt, filename, content)

        item.vendor = fields.vendor
        item.category = fields.category
        item.transaction_date = (
            date.fromisoformat(fields.transaction_date) if fields.transaction_date else None
        )
        item.amount = fields.amount
        item.currency = fields.currency or "USD"
        item.payment_method = fields.payment_method
        item.extracted_fields = fields.model_dump()

        # Verdict
        verdict_result = await compute_verdict(
            fields=fields,
            snapshot_grade=sub.snapshot_grade,
            snapshot_department=sub.snapshot_department,
            db=db,
        )

        item.verdict = verdict_result.verdict
        item.effective_verdict = verdict_result.verdict
        item.confidence = verdict_result.confidence
        item.reasoning = verdict_result.reasoning
        item.citations = [c.model_dump() for c in verdict_result.citations]
        item.retrieval_score = verdict_result.retrieval_score

        db.add(AuditLog(
            id=uuid.uuid4(),
            submission_id=submission_id,
            line_item_id=line_item_id,
            action=AuditAction.ai_verdict.value,
            actor_type=ActorType.system.value,
            new_value={
                "verdict": verdict_result.verdict,
                "confidence": verdict_result.confidence,
                "gate_applied": verdict_result.gate_applied,
            },
        ))

        await db.commit()

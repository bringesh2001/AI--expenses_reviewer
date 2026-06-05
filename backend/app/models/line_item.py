import uuid
from datetime import date, datetime
from enum import Enum
from sqlalchemy import String, Date, DateTime, Numeric, Float, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..database import Base


class LineItemCategory(str, Enum):
    airfare = "airfare"
    lodging = "lodging"
    meal = "meal"
    ground_transport = "ground_transport"
    entertainment = "entertainment"
    other = "other"


class VerdictType(str, Enum):
    compliant = "compliant"
    flagged = "flagged"
    needs_review = "needs_review"
    rejected = "rejected"


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receipt_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Raw extracted fields from the receipt (schema-constrained JSON from LLM)
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # AI verdict
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{chunk_id, section, text, score}]
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Reviewer override (if any)
    override_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Effective verdict = override_verdict if set, else verdict
    effective_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["Submission"] = relationship("Submission", back_populates="line_items")  # noqa: F821
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="line_item")  # noqa: F821

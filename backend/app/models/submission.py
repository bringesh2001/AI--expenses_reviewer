import uuid
from datetime import date, datetime
from enum import Enum
from sqlalchemy import String, Integer, Date, DateTime, Numeric, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ENUM
from ..database import Base


class SubmissionStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    reviewing = "reviewing"
    approved = "approved"
    rejected = "rejected"
    needs_revision = "needs_revision"


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True
    )
    trip_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    trip_destination: Mapped[str] = mapped_column(String(200), nullable=False)
    trip_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    trip_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SubmissionStatus.draft.value)
    total_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Context snapshot (frozen at submission time — grade/dept may change later)
    snapshot_grade: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_department: Mapped[str] = mapped_column(String(100), nullable=False)

    # Review metadata
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped["Employee"] = relationship("Employee", back_populates="submissions", foreign_keys=[employee_id])  # noqa: F821
    line_items: Mapped[list["LineItem"]] = relationship("LineItem", back_populates="submission", cascade="all, delete-orphan")  # noqa: F821
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="submission", cascade="all, delete-orphan")  # noqa: F821

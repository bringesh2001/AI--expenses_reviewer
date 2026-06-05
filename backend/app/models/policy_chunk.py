import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector
from ..database import Base
from ..config import settings


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # e.g. TEP-001
    section: Mapped[str] = mapped_column(String(50), nullable=False)               # e.g. §3.2
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    domain_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)         # ["lodging","tier2"]
    source_file: Mapped[str] = mapped_column(String(200), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Hybrid retrieval columns
    embedding: Mapped[list | None] = mapped_column(Vector(settings.embedding_dim), nullable=True)
    ts_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_policy_chunks_ts_vector", "ts_vector", postgresql_using="gin"),
        Index(
            "ix_policy_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 50},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

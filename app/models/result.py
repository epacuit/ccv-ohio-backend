# app/models/result.py
from sqlalchemy import Column, Integer, Boolean, TIMESTAMP, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from .base import Base

class Result(Base):
    __tablename__ = "results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    poll_id = Column(UUID(as_uuid=True), ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Complete results as JSONB
    data = Column(JSONB, nullable=False)
    # Includes: winners, explanation, pairwise_matrix, support_matrix, ballot_statistics
    
    # Metadata
    computed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    computation_time_ms = Column(Integer, nullable=True)
    is_current = Column(Boolean, default=True, nullable=False)
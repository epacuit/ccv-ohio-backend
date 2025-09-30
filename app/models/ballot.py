# app/models/ballot.py
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from .base import Base

class Ballot(Base):
    __tablename__ = "ballots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    poll_id = Column(UUID(as_uuid=True), ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Rankings as JSONB
    rankings = Column(JSONB, nullable=False)
    # Structure: [{"candidate_id": "uuid", "rank": 1}, {"candidate_id": "uuid", "rank": 2}]
    
    # Count for aggregation
    count = Column(Integer, default=1, nullable=False)
    
    write_ins = Column(JSONB, nullable=True, default=[])

    # Voter identification
    voter_fingerprint = Column(String(64), nullable=True)
    voter_token = Column(String(64), nullable=True)
    
    # Metadata
    submitted_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
    ip_hash = Column(String(64), nullable=True)
    
    # Import tracking
    import_batch_id = Column(String(100), nullable=True)
    is_test = Column(Boolean, default=False, nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('poll_id', 'voter_fingerprint', name='uq_ballot_fingerprint'),
        UniqueConstraint('poll_id', 'voter_token', name='uq_ballot_token'),
    )

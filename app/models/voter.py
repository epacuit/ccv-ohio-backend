# app/models/voter.py
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .base import Base

class Voter(Base):
    __tablename__ = "voters"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    poll_id = Column(UUID(as_uuid=True), ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Email and hash
    email = Column(String(255), nullable=False)
    email_hash = Column(String(64), nullable=False)  # SHA256 hash for privacy
    
    # Access token
    token = Column(String(64), nullable=False, unique=True)
    
    # Invitation tracking
    invitation_sent = Column(Boolean, default=False, nullable=False)
    invitation_sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    reminder_sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('poll_id', 'email', name='uq_voter_poll_email'),
        UniqueConstraint('poll_id', 'email_hash', name='uq_voter_poll_email_hash'),
    )
# app/models/poll.py

from sqlalchemy import Column, String, Boolean, TIMESTAMP, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from .base import Base
from .poll_settings import DEFAULT_SETTINGS  # Add this import

class Poll(Base):
    __tablename__ = "polls"
    
    # Identification
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    short_id = Column(String(8), unique=True, nullable=False, index=True)
    slug = Column(String(50), unique=True, nullable=True)
    
    # Basic info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Poll type and status
    is_private = Column(Boolean, default=False, nullable=False)
    is_test = Column(Boolean, default=False, nullable=False)  
    status = Column(String(20), default='open', nullable=False)
    closing_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Candidates as JSONB (choose the name you prefer)
    candidates = Column(JSONB, nullable=False, default=list)  
    # Structure: [{"id": "uuid", "name": "Pizza", "long_name": "...", "description": "...", "image_url": "...", "is_write_in": false}]
    
    # Settings as JSONB
    settings = Column(JSONB, nullable=False, default=DEFAULT_SETTINGS)
    
    # Owner management
    owner_email = Column(String(255), nullable=True, index=True)
    admin_token = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

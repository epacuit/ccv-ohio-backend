## app/schemas/poll.py
 
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class CandidateSchema(BaseModel):
    id: str
    name: str
    long_name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_write_in: bool = False

class PollSettingsSchema(BaseModel):
    allow_ties: bool = True
    require_complete_ranking: bool = False
    randomize_options: bool = False
    allow_write_ins: bool = False
    allow_vote_updates: bool = True  # Allow voters to change their vote
    show_live_results: bool = False
    results_visibility: str = "public"
    anonymize_voters: bool = True

class PollCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_private: bool = False
    is_test: bool = False
    settings: Optional[PollSettingsSchema] = None
    closing_at: Optional[datetime] = None
    owner_email: Optional[str] = None
    slug: Optional[str] = Field(None, pattern="^[a-z0-9-]+$", min_length=3, max_length=50)

class PollResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    short_id: str
    slug: Optional[str]
    title: str
    description: Optional[str]
    is_private: bool
    status: str
    candidates: List[Dict[str, Any]]
    settings: Dict[str, Any]
    created_at: datetime
    
class PollAdminResponse(PollResponse):
    admin_token: str
    owner_email: Optional[str]
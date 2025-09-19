# app/schemas/ballot.py
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

class RankingItem(BaseModel):
    candidate_id: str
    rank: int = Field(..., ge=1)

class BallotSubmit(BaseModel):
    poll_id: UUID
    rankings: List[RankingItem]
    voter_fingerprint: Optional[str] = None
    voter_token: Optional[str] = None

class BallotResponse(BaseModel):
    success: bool
    message: str
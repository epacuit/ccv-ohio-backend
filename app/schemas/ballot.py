# app/schemas/ballot.py
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class PairwiseChoice(BaseModel):
    cand1_id: str
    cand2_id: str
    choice: str  # "cand1", "cand2", or "tie"

class BallotSubmit(BaseModel):
    poll_id: UUID
    pairwise_choices: List[PairwiseChoice]
    voter_fingerprint: Optional[str] = None
    voter_token: Optional[str] = None

class BallotResponse(BaseModel):
    success: bool
    message: str

from typing import Optional
from pydantic import BaseModel

class PollSettings(BaseModel):
    """Defines all valid poll settings with types and defaults"""
    allow_ties: bool = True
    require_complete_ranking: bool = False
    randomize_options: bool = False
    allow_write_ins: bool = False
    show_live_results: bool = False
    results_visibility: str = "public"  # public|voters|owner
    anonymize_voters: bool = True
    ballot_processing_rule: str = "alaska"  # "alaska" or "truncation"
    
    class Config:
        # Allow extra fields for future expansion
        extra = "allow"

# Default settings instance
DEFAULT_SETTINGS = PollSettings().model_dump()

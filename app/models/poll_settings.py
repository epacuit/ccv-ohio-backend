from pydantic import BaseModel

class PollSettings(BaseModel):
    """Defines all valid poll settings with types and defaults"""
    require_all_matchups: bool = False
    randomize_options: bool = False
    allow_vote_updates: bool = True
    show_live_results: bool = False
    results_visibility: str = "public"  # public|voters|owner
    anonymize_voters: bool = True

    class Config:
        extra = "allow"

# Default settings instance
DEFAULT_SETTINGS = PollSettings().model_dump()

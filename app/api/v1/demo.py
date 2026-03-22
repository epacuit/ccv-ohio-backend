# app/api/v1/demo.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from fastapi.encoders import jsonable_encoder
import numpy as np
import time

from app.services.voting_calculation import calculate_mwsl_with_explanation

router = APIRouter()

class DemoPairwiseChoice(BaseModel):
    cand1_id: str
    cand2_id: str
    choice: str  # "cand1", "cand2", "tie", or "neither"

class DemoBallot(BaseModel):
    pairwise_choices: List[DemoPairwiseChoice]
    count: int = Field(default=1, ge=1)

class DemoCandidate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class DemoCalculateRequest(BaseModel):
    candidates: List[DemoCandidate]
    ballots: List[DemoBallot]

@router.post("/calculate")
async def calculate_demo_results(request: DemoCalculateRequest):
    """
    Calculate voting results for demo purposes WITHOUT saving to database.
    
    This endpoint takes a list of candidates and ballots, calculates the
    MWSL (Most Wins, Smallest Loss) results using the same algorithm as
    the main voting system, but doesn't persist anything.
    
    Perfect for demos, testing, and educational purposes.
    """
    
    if not request.candidates:
        raise HTTPException(status_code=400, detail="At least one candidate required")
    
    if not request.ballots:
        return {
            "status": "no_votes",
            "message": "No ballots submitted",
            "statistics": {
                "total_votes": 0
            }
        }
    
    # Convert request data to format expected by calculation engine
    candidates_dict = [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description
        }
        for c in request.candidates
    ]
    
    # Create mock ballot objects that match the expected structure
    # CRITICAL: Must accept keyword arguments for consolidate_write_ins_in_ballots
    class MockBallot:
        def __init__(self, poll_id=None, pairwise_choices=None, count=1,
                     voter_fingerprint=None, voter_token=None,
                     ip_hash=None, import_batch_id=None, is_test=True):
            self.poll_id = poll_id or "demo"
            self.pairwise_choices = pairwise_choices or []
            self.count = count
            self.write_ins = []  # Empty - demo doesn't support write-ins
            self.voter_fingerprint = voter_fingerprint
            self.voter_token = voter_token
            self.ip_hash = ip_hash
            self.import_batch_id = import_batch_id
            self.is_test = is_test
            self.updated_at = None

        def __repr__(self):
            return f"MockBallot(pairwise_choices={self.pairwise_choices}, count={self.count})"

    try:
        mock_ballots = [
            MockBallot(
                poll_id="demo",
                pairwise_choices=[{"cand1_id": c.cand1_id, "cand2_id": c.cand2_id, "choice": c.choice} for c in ballot.pairwise_choices],
                count=ballot.count
            )
            for ballot in request.ballots
        ]
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error creating ballots: {str(e)}"
        )
    
    # Calculate results
    try:
        start_time = time.time()
        
        # Log for debugging
        print(f"Demo calculation: {len(mock_ballots)} ballots, {len(candidates_dict)} candidates")
        print(f"First ballot sample: {mock_ballots[0] if mock_ballots else 'No ballots'}")
        
        results_data = calculate_mwsl_with_explanation(
            ballots=mock_ballots,
            candidates=candidates_dict
        )
        computation_time_ms = int((time.time() - start_time) * 1000)
        
        # Convert NumPy types to JSON-serializable Python types
        results_data = jsonable_encoder(
            results_data,
            custom_encoder={
                np.integer: int,
                np.floating: float,
                np.ndarray: lambda a: a.tolist(),
            },
        )
        
        # Add metadata
        results_data["computation_time_ms"] = computation_time_ms
        results_data["is_demo"] = True
        
        return results_data
        
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"ERROR in demo calculation: {str(e)}")
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating results: {str(e)}"
        )

@router.get("/health")
async def demo_health():
    """Health check for demo endpoint"""
    return {"status": "ok", "endpoint": "demo"}
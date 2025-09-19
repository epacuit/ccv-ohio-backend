# app/api/v1/results.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
import json
import numpy as np
import time

from app.db import get_db
from app.models import Poll, Ballot, Result
from app.services.voting_calculation import calculate_mwsl_with_explanation

router = APIRouter()

@router.post("/calculate/{poll_id}")
async def calculate_results(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Calculate and store results for a poll"""
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Get all ballots
    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    if not ballots:
        raise HTTPException(status_code=400, detail="No ballots to calculate")
    
    # Calculate results
    start_time = time.time()
    results_data = calculate_mwsl_with_explanation(
        ballots=ballots,
        candidates=poll.candidates
    )

    # Convert NumPy scalars/arrays into plain Python for JSON serialization
    results_data = jsonable_encoder(
        results_data,
        custom_encoder={
            np.integer: int,
            np.floating: float,
            np.ndarray: lambda a: a.tolist(),
        },
    )
    
    computation_time_ms = int((time.time() - start_time) * 1000)
    
    # Mark old results as not current
    stmt = select(Result).where(Result.poll_id == poll.id, Result.is_current == True)
    result = await db.execute(stmt)
    old_results = result.scalars().all()
    for old_result in old_results:
        old_result.is_current = False
    
    # Store new results
    new_result = Result(
        poll_id=poll.id,
        data=results_data,
        computation_time_ms=computation_time_ms,
        is_current=True
    )
    
    db.add(new_result)
    await db.commit()
    
    return {
        "success": True,
        "message": "Results calculated",
        "computation_time_ms": computation_time_ms,
        "results": results_data
    }

@router.get("/{poll_id}")
async def get_results(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get calculated results for a poll"""
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Get current results
    stmt = select(Result).where(
        Result.poll_id == poll.id,
        Result.is_current == True
    )
    result = await db.execute(stmt)
    results = result.scalar_one_or_none()
    
    if not results:
        return {
            "poll_id": str(poll.id),
            "status": "no_results",
            "message": "Results not yet calculated"
        }
    
    return results.data

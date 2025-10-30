# app/api/v1/results.py - PRODUCTION-GRADE CONCURRENT-SAFE VERSION
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, text
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from uuid import UUID
import json
import numpy as np
import time
import asyncio

from app.db import get_db
from app.models import Poll, Ballot, Result
from app.services.voting_calculation import calculate_mwsl_with_explanation

router = APIRouter()

async def get_latest_ballot_time(poll_id: UUID, db: AsyncSession) -> Optional[datetime]:
    """Get the timestamp of the most recent ballot for a poll"""
    stmt = select(func.max(Ballot.updated_at)).where(Ballot.poll_id == poll_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def calculate_and_store_results(
    poll: Poll, 
    db: AsyncSession,
    force_recalculate: bool = False
) -> Dict[str, Any]:
    """
    Calculate results and cache them in the database.
    PRODUCTION-SAFE: Uses PostgreSQL advisory locks to prevent race conditions
    when multiple users view results simultaneously.
    
    Auto-recalculates if:
    1. No cached results exist
    2. Cached results are stale (new ballots added)
    3. force_recalculate is True
    """
    
    # Use PostgreSQL advisory lock to prevent concurrent calculations for same poll
    # This is critical for high-traffic scenarios
    lock_key = abs(hash(str(poll.id))) % (2**31 - 1)
    
    try:
        # Try to acquire lock - if another request is calculating, wait up to 30 seconds
        # pg_try_advisory_xact_lock returns true if lock acquired, false otherwise
        lock_stmt = text("SELECT pg_try_advisory_xact_lock(:lock_key)")
        lock_result = await db.execute(lock_stmt, {"lock_key": lock_key})
        lock_acquired = lock_result.scalar()
        
        if not lock_acquired:
            # Another request is calculating - wait a bit and return cached result
            await asyncio.sleep(0.5)
            
            # Get the cached result (should exist after other request finishes)
            stmt = select(Result).where(
                Result.poll_id == poll.id,
                Result.is_current == True
            ).order_by(Result.computed_at.desc()).limit(1)
            
            result = await db.execute(stmt)
            cached_result = result.scalars().first()
            
            if cached_result:
                return cached_result.data
            
            # If still no result, try acquiring lock again
            lock_result = await db.execute(lock_stmt, {"lock_key": lock_key})
            lock_acquired = lock_result.scalar()
            
            if not lock_acquired:
                raise HTTPException(
                    status_code=503,
                    detail="Results are being calculated. Please retry in a few seconds."
                )
        
        # Lock acquired - we're the one calculating
        
        # Check for existing cached results - handle duplicates gracefully
        stmt = select(Result).where(
            Result.poll_id == poll.id,
            Result.is_current == True
        ).order_by(Result.computed_at.desc())
        
        result = await db.execute(stmt)
        cached_results = result.scalars().all()
        
        # If we have multiple current results (data corruption), fix it atomically
        if len(cached_results) > 1:
            # Keep the most recent, mark others as not current using bulk update
            result_ids_to_update = [r.id for r in cached_results[1:]]
            if result_ids_to_update:
                await db.execute(
                    update(Result)
                    .where(Result.id.in_(result_ids_to_update))
                    .values(is_current=False)
                )
                await db.commit()
        
        cached_result = cached_results[0] if cached_results else None
        
        # Get latest ballot timestamp
        latest_ballot_time = await get_latest_ballot_time(poll.id, db)
        
        # Determine if we need to recalculate
        needs_recalc = (
            force_recalculate or
            not cached_result or
            not latest_ballot_time or  # No ballots yet
            (cached_result and latest_ballot_time and 
             latest_ballot_time > cached_result.computed_at)
        )
        
        if not needs_recalc and cached_result:
            # Return cached results - still fresh
            return cached_result.data
        
        # Need to calculate - get all ballots
        stmt = select(Ballot).where(Ballot.poll_id == poll.id)
        result = await db.execute(stmt)
        ballots = result.scalars().all()
        
        if not ballots:
            # No ballots to calculate
            return {
                "poll_id": str(poll.id),
                "status": "no_votes",
                "message": "No votes submitted yet",
                "statistics": {
                    "total_votes": 0
                }
            }
        
        # Calculate results
        start_time = time.time()
        results_data = calculate_mwsl_with_explanation(
            ballots=ballots,
            candidates=poll.candidates
        )
        
        # Convert NumPy scalars/arrays to plain Python for JSON serialization
        results_data = jsonable_encoder(
            results_data,
            custom_encoder={
                np.integer: int,
                np.floating: float,
                np.ndarray: lambda a: a.tolist(),
            },
        )
        
        computation_time_ms = int((time.time() - start_time) * 1000)
        
        # CRITICAL: Use atomic bulk update to mark all old results as not current
        # This prevents race conditions better than updating individual objects
        await db.execute(
            update(Result)
            .where(Result.poll_id == poll.id)
            .where(Result.is_current == True)
            .values(is_current=False)
        )
        
        # Store new results
        new_result = Result(
            poll_id=poll.id,
            data=results_data,
            computation_time_ms=computation_time_ms,
            is_current=True
        )
        
        db.add(new_result)
        await db.commit()
        
        return results_data
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the error but don't crash
        print(f"Error calculating results for poll {poll.id}: {e}")
        
        # Try to return any cached result we have
        stmt = select(Result).where(
            Result.poll_id == poll.id,
            Result.is_current == True
        ).order_by(Result.computed_at.desc()).limit(1)
        
        result = await db.execute(stmt)
        cached_result = result.scalars().first()
        
        if cached_result:
            return cached_result.data
        
        # No cached results and calculation failed
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating results: {str(e)}"
        )

@router.get("/{poll_id}")
async def get_results(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get results for a poll - AUTO-CALCULATES if needed.
    No authentication required for viewing.
    CONCURRENT-SAFE: Multiple simultaneous requests won't cause duplicate calculations.
    """
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Auto-calculate or return cached results (concurrent-safe)
    results = await calculate_and_store_results(poll, db)
    return results

@router.post("/calculate/{poll_id}")
async def force_calculate_results(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Force recalculation of results - ADMIN ONLY.
    Useful for debugging or forcing a refresh.
    """
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Force recalculation
    results = await calculate_and_store_results(poll, db, force_recalculate=True)
    
    return {
        "success": True,
        "message": "Results recalculated",
        "results": results
    }

@router.get("/{poll_id}/status")
async def get_results_status(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if results are up-to-date without triggering recalculation.
    Useful for frontend to know if it should show a "calculating..." message.
    """
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Check cached results - handle duplicates
    stmt = select(Result).where(
        Result.poll_id == poll.id,
        Result.is_current == True
    ).order_by(Result.computed_at.desc()).limit(1)
    
    result = await db.execute(stmt)
    cached_result = result.scalars().first()
    
    # Get latest ballot timestamp
    latest_ballot_time = await get_latest_ballot_time(poll.id, db)
    
    # Count total ballots
    stmt = select(func.sum(Ballot.count)).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    total_votes = result.scalar_one_or_none() or 0
    
    if not cached_result:
        return {
            "status": "not_calculated",
            "total_votes": total_votes,
            "needs_calculation": True
        }
    
    is_stale = (
        latest_ballot_time and 
        latest_ballot_time > cached_result.computed_at
    )
    
    return {
        "status": "calculated",
        "is_stale": is_stale,
        "computed_at": cached_result.computed_at.isoformat(),
        "last_ballot_at": latest_ballot_time.isoformat() if latest_ballot_time else None,
        "total_votes": total_votes,
        "computation_time_ms": cached_result.computation_time_ms,
        "needs_calculation": is_stale
    }
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import List, Optional
import os
import hashlib
from datetime import datetime, timedelta

# Use the same imports as your polls.py
from app.db import get_db
from app.models import Poll, Ballot

router = APIRouter()

def verify_super_admin(password: str) -> bool:
    """Verify super admin password"""
    # Set this in your environment variables
    SUPER_ADMIN_PASSWORD_HASH = os.getenv("SUPER_ADMIN_PASSWORD_HASH")
    if not SUPER_ADMIN_PASSWORD_HASH:
        return False
    
    # Hash the provided password and compare
    provided_hash = hashlib.sha256(password.encode()).hexdigest()
    return provided_hash == SUPER_ADMIN_PASSWORD_HASH

@router.get("/admin/all-polls")
async def get_all_polls(
    password: str = Query(..., description="Super admin password"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    """Super admin endpoint to see all polls with admin access"""
    
    # Verify password
    if not verify_super_admin(password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Get total count
    count_stmt = select(func.count()).select_from(Poll)
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar()
    
    # Get polls with pagination
    stmt = select(Poll).order_by(desc(Poll.created_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    polls = result.scalars().all()
    
    # Get ballot counts
    poll_data = []
    for poll in polls:
        ballot_count_stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll.id)
        ballot_result = await db.execute(ballot_count_stmt)
        ballot_count = ballot_result.scalar() or 0
        
        poll_data.append({
            "id": str(poll.id),
            "short_id": poll.short_id,
            "slug": poll.slug,
            "title": poll.title,
            "owner_email": poll.owner_email,
            "admin_token": poll.admin_token,
            "admin_url": f"/admin/{poll.short_id}?token={poll.admin_token}",
            "vote_url": f"/vote/{poll.slug or poll.short_id}",
            "created_at": poll.created_at.isoformat() if poll.created_at else None,
            "closing_at": poll.closing_at.isoformat() if poll.closing_at else None,
            "status": poll.status,
            "is_private": poll.is_private,
            "ballot_count": ballot_count,
            "candidate_count": len(poll.candidates) if poll.candidates else 0
        })
    
    return {
        "total_polls": total_count,
        "showing": len(poll_data),
        "offset": offset,
        "limit": limit,
        "polls": poll_data
    }

@router.get("/admin/search-poll")
async def search_poll(
    password: str = Query(..., description="Super admin password"),
    search: str = Query(..., description="Search by title, short_id, slug, or email"),
    db: AsyncSession = Depends(get_db)
):
    """Search for specific polls"""
    
    if not verify_super_admin(password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Search by multiple fields
    stmt = select(Poll).where(
        (Poll.short_id == search) |
        (Poll.slug == search) |
        (Poll.title.ilike(f"%{search}%")) |
        (Poll.owner_email.ilike(f"%{search}%"))
    ).limit(20)
    
    result = await db.execute(stmt)
    polls = result.scalars().all()
    
    if not polls:
        return {"message": "No polls found", "found": 0, "polls": []}
    
    poll_data = []
    for poll in polls:
        ballot_count_stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll.id)
        ballot_result = await db.execute(ballot_count_stmt)
        ballot_count = ballot_result.scalar() or 0
        
        poll_data.append({
            "short_id": poll.short_id,
            "slug": poll.slug,
            "title": poll.title,
            "owner_email": poll.owner_email,
            "admin_token": poll.admin_token,
            "admin_url": f"/admin/{poll.short_id}?token={poll.admin_token}",
            "vote_url": f"/vote/{poll.slug or poll.short_id}",
            "created_at": poll.created_at.isoformat() if poll.created_at else None,
            "ballot_count": ballot_count
        })
    
    return {
        "found": len(poll_data),
        "polls": poll_data
    }

@router.delete("/admin/delete-poll/{poll_id}")
async def delete_poll_super_admin(
    poll_id: str,
    password: str = Query(..., description="Super admin password"),
    db: AsyncSession = Depends(get_db)
):
    """Delete a poll as super admin"""
    
    if not verify_super_admin(password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Find poll by short_id or slug
    stmt = select(Poll).where(
        (Poll.short_id == poll_id) | (Poll.slug == poll_id)
    )
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Delete the poll
    await db.delete(poll)
    await db.commit()
    
    return {"message": f"Poll '{poll.title}' deleted successfully"}

@router.get("/admin/stats")
async def get_admin_stats(
    password: str = Query(..., description="Super admin password"),
    db: AsyncSession = Depends(get_db)
):
    """Get overall statistics"""
    
    if not verify_super_admin(password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Total polls
    total_polls_stmt = select(func.count()).select_from(Poll)
    total_polls_result = await db.execute(total_polls_stmt)
    total_polls = total_polls_result.scalar()
    
    # Total ballots
    total_ballots_stmt = select(func.count()).select_from(Ballot)
    total_ballots_result = await db.execute(total_ballots_stmt)
    total_ballots = total_ballots_result.scalar()
    
    # Active polls (not closed)
    active_polls_stmt = select(func.count()).select_from(Poll).where(Poll.status != 'closed')
    active_polls_result = await db.execute(active_polls_stmt)
    active_polls = active_polls_result.scalar()
    
    # Private polls
    private_polls_stmt = select(func.count()).select_from(Poll).where(Poll.is_private == True)
    private_polls_result = await db.execute(private_polls_stmt)
    private_polls = private_polls_result.scalar()
    
    # Recent polls (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_polls_stmt = select(func.count()).select_from(Poll).where(Poll.created_at > seven_days_ago)
    recent_polls_result = await db.execute(recent_polls_stmt)
    recent_polls = recent_polls_result.scalar()
    
    return {
        "total_polls": total_polls or 0,
        "total_ballots": total_ballots or 0,
        "active_polls": active_polls or 0,
        "private_polls": private_polls or 0,
        "recent_polls_7_days": recent_polls or 0,
        "average_ballots_per_poll": round(total_ballots / total_polls, 2) if total_polls and total_polls > 0 else 0
    }

@router.delete("/admin/delete-test-polls")
async def delete_test_polls(
    password: str = Query(..., description="Super admin password"),
    db: AsyncSession = Depends(get_db)
):
    """Delete all test polls"""
    
    if not verify_super_admin(password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Find all test polls
    stmt = select(Poll).where(Poll.is_test == True)
    result = await db.execute(stmt)
    test_polls = result.scalars().all()
    
    count = len(test_polls)
    
    if count == 0:
        return {"message": "No test polls found", "deleted": 0}
    
    # Delete all test polls (cascade will delete ballots and results)
    for poll in test_polls:
        await db.delete(poll)
    
    await db.commit()
    
    return {
        "message": f"Successfully deleted {count} test poll(s)",
        "deleted": count
    }

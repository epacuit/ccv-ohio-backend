# app/api/v1/ballots.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
import hashlib

from app.db import get_db
from app.models import Ballot, Poll

router = APIRouter()

def hash_fingerprint(fingerprint: str) -> str:
    """Hash fingerprint for privacy"""
    return hashlib.sha256(fingerprint.encode()).hexdigest() if fingerprint else None

def hash_ip(ip_address: str) -> str:
    """Hash IP for privacy"""
    return hashlib.sha256(ip_address.encode()).hexdigest() if ip_address else None

@router.post("/")
async def submit_ballot(
    ballot_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Submit or update a ballot - matches MongoDB API"""
    
    # Parse poll_id
    poll_id = ballot_data.get('poll_id')
    if isinstance(poll_id, str):
        poll_id = UUID(poll_id)
    
    # Get poll and check if open
    stmt = select(Poll).where(Poll.id == poll_id)
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Check if poll is open
    if poll.status == 'closed':
        return {"success": False, "message": "Poll is closed"}
    
    if poll.closing_at and poll.closing_at < datetime.now(timezone.utc):
        # Poll should be closed but status not updated
        poll.status = 'closed'
        await db.commit()
        return {"success": False, "message": "Poll is closed"}
    
    # Hash sensitive data
    voter_fingerprint = hash_fingerprint(ballot_data.get('voter_fingerprint'))
    voter_token = ballot_data.get('voter_token')  # Don't hash tokens - they're already random
    ip_hash = hash_ip(ballot_data.get('ip_address'))
    
    # Check for existing ballot
    existing_ballot = None
    
    if poll.is_private and voter_token:
        # Private poll - check by token
        stmt = select(Ballot).where(
            Ballot.poll_id == poll_id,
            Ballot.voter_token == voter_token
        )
        result = await db.execute(stmt)
        existing_ballot = result.scalar_one_or_none()
    elif voter_fingerprint:
        # Public poll - check by fingerprint
        stmt = select(Ballot).where(
            Ballot.poll_id == poll_id,
            Ballot.voter_fingerprint == voter_fingerprint
        )
        result = await db.execute(stmt)
        existing_ballot = result.scalar_one_or_none()
    
    if existing_ballot:
        # Update existing ballot
        existing_ballot.rankings = ballot_data['rankings']
        existing_ballot.updated_at = datetime.now(timezone.utc)
        existing_ballot.ip_hash = ip_hash
        
        await db.commit()
        
        return {
            "success": True,
            "message": "Vote updated"
        }
    else:
        # Create new ballot
        ballot = Ballot(
            poll_id=poll_id,
            rankings=ballot_data['rankings'],
            count=ballot_data.get('count', 1),
            voter_fingerprint=voter_fingerprint,
            voter_token=voter_token,
            ip_hash=ip_hash,
            import_batch_id=ballot_data.get('import_batch_id'),
            is_test=ballot_data.get('is_test', False)
        )
        
        db.add(ballot)
        await db.commit()
        
        return {
            "success": True,
            "message": "Vote recorded"
        }

@router.get("/poll/{poll_id}")
async def get_poll_ballots(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get all ballots for a poll - admin only"""
    
    # Find poll by ID or short_id
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
    
    # Return in MongoDB format
    return [
        {
            "id": str(b.id),
            "rankings": b.rankings,
            "count": b.count,
            "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            "is_test": b.is_test
        }
        for b in ballots
    ]

@router.post("/bulk-import")
async def bulk_import_ballots(
    import_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Bulk import ballots from CSV - admin only"""
    
    poll_id = import_data.get('poll_id')
    admin_token = import_data.get('admin_token')
    ballots_data = import_data.get('ballots', [])
    
    if isinstance(poll_id, str):
        poll_id = UUID(poll_id)
    
    # Get poll and verify admin
    stmt = select(Poll).where(Poll.id == poll_id)
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Aggregate identical ballots for efficiency
    from collections import defaultdict
    ranking_counts = defaultdict(int)
    
    for ballot in ballots_data:
        # Create hashable key from rankings
        ranking_key = tuple(
            (r['candidate_id'], r['rank']) 
            for r in sorted(ballot['rankings'], key=lambda x: (x['rank'], x['candidate_id']))
        )
        count = ballot.get('count', 1)
        ranking_counts[ranking_key] += count
    
    # Create ballot records
    import_batch_id = f"import_{poll_id}_{datetime.now(timezone.utc).isoformat()}"
    created_count = 0
    total_votes = 0
    
    for ranking_tuple, count in ranking_counts.items():
        # Convert back to rankings format
        rankings = [
            {"candidate_id": cid, "rank": rank}
            for cid, rank in ranking_tuple
        ]
        
        ballot = Ballot(
            poll_id=poll_id,
            rankings=rankings,
            count=count,
            import_batch_id=import_batch_id,
            is_test=False
        )
        
        db.add(ballot)
        created_count += 1
        total_votes += count
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Imported {total_votes} votes in {created_count} ballot records",
        "import_batch_id": import_batch_id,
        "unique_patterns": created_count,
        "total_votes": total_votes
    }

@router.delete("/poll/{poll_id}/clear")
async def clear_poll_ballots(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Clear all ballots for a poll - admin only"""
    
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
    
    # Delete all ballots for this poll
    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    count = len(ballots)
    for ballot in ballots:
        await db.delete(ballot)
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Deleted {count} ballot records"
    }
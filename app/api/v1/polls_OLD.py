# app/api/v1/polls.py - FINAL VERSION WITH WRITE-IN SUPPORT
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4
import secrets
import string
import random
import os
import json

from app.db import get_db
from app.models import Poll, Ballot

router = APIRouter()

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000")

def generate_short_id(length: int = 6) -> str:
    """Generate a random short ID"""
    chars = string.ascii_letters + string.digits
    chars = chars.replace('0', '').replace('O', '').replace('l', '').replace('I', '')
    return ''.join(random.choice(chars) for _ in range(length))

def get_poll_status(poll) -> str:
    """Determine if poll is open or closed"""
    if poll.status == 'closed':
        return 'closed'
    if poll.closing_at and poll.closing_at < datetime.now(timezone.utc):
        return 'closed'
    return 'open'

def generate_candidate_id(index: int = None, is_write_in: bool = False) -> str:
    """
    Generate a consistent candidate ID.
    Regular candidates: candidate-0, candidate-1, etc.
    Write-ins: write-in-{uuid} to avoid collisions
    """
    if is_write_in:
        return f"write-in-{uuid4().hex[:8]}"
    elif index is not None:
        return f"candidate-{index}"
    else:
        return f"candidate-{uuid4().hex[:8]}"

def ensure_candidates_have_ids(candidates: List[Any]) -> List[Dict[str, Any]]:
    """
    Ensure every candidate has a unique ID.
    This is THE single source of truth for candidate IDs.
    """
    processed_candidates = []
    
    for idx, candidate in enumerate(candidates):
        if isinstance(candidate, dict):
            if candidate.get('id'):
                # Already has an ID - keep it
                processed_candidates.append(candidate)
            else:
                # No ID - create one based on index
                processed_candidates.append({
                    **candidate,
                    'id': generate_candidate_id(idx, False)
                })
        elif isinstance(candidate, str):
            # Simple string candidate - convert to dict with ID
            processed_candidates.append({
                'id': generate_candidate_id(idx, False),
                'name': candidate,
                'description': None
            })
        else:
            # Fallback for any other type
            processed_candidates.append({
                'id': generate_candidate_id(idx, False),
                'name': str(candidate),
                'description': None
            })
    
    return processed_candidates

@router.post("/")
async def create_poll(
    poll_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Create a new poll with properly structured candidates"""
    
    # Generate unique short_id
    while True:
        short_id = generate_short_id()
        stmt = select(Poll).where(Poll.short_id == short_id)
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            break
    
    # Handle custom slugs if requested
    slug = poll_data.get('slug')
    if slug:
        allowed_emails = json.loads(os.getenv("SLUG_ALLOWED_EMAILS", "[]"))
        if poll_data.get('owner_email') not in allowed_emails:
            slug = None
    
    # CRITICAL: Ensure all candidates have IDs before storing
    candidates_with_ids = ensure_candidates_have_ids(poll_data.get('candidates', []))
    
    # Create poll
    poll = Poll(
        short_id=short_id,
        slug=slug,
        title=poll_data['title'],
        description=poll_data.get('description'),
        candidates=candidates_with_ids,  # Guaranteed to have IDs
        settings=poll_data.get('settings', {}),
        is_private=poll_data.get('is_private', False),
        status='open',
        closing_at=poll_data.get('closing_at'),
        owner_email=poll_data.get('owner_email'),
        admin_token=secrets.token_urlsafe(32),
        password_hash=poll_data.get('password_hash')
    )
    
    db.add(poll)
    await db.commit()
    await db.refresh(poll)
    
    # Return with candidates to confirm IDs
    return {
        "id": str(poll.id),
        "short_id": poll.short_id,
        "slug": poll.slug,
        "admin_token": poll.admin_token,
        "url": f"{BASE_URL}/p/{poll.short_id}",
        "qr_code": f"{BASE_URL}/qr/{poll.short_id}.png",
        "candidates": poll.candidates  # Include for verification
    }

@router.get("/by-owner")
async def get_polls_by_owner(
    email: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get all polls for an owner with proper ballot counts"""
    
    # Subquery for ballot counts
    ballot_count = select(
        Ballot.poll_id,
        func.sum(Ballot.count).label('total_ballots')
    ).group_by(Ballot.poll_id).subquery()
    
    # Main query with left join
    stmt = select(
        Poll,
        func.coalesce(ballot_count.c.total_ballots, 0).label('total_ballots')
    ).outerjoin(
        ballot_count, Poll.id == ballot_count.c.poll_id
    ).where(
        Poll.owner_email == email
    ).order_by(Poll.created_at.desc())
    
    result = await db.execute(stmt)
    
    poll_list = []
    for p, total_ballots in result:
        poll_list.append({
            "id": str(p.id),
            "short_id": p.short_id,
            "title": p.title,
            "status": get_poll_status(p),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "total_ballots": int(total_ballots)
        })
    
    return poll_list

@router.get("/{poll_id}")
async def get_poll(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get poll with properly structured candidates"""
    
    poll = None
    
    # Try as short_id first
    stmt = select(Poll).where(Poll.short_id == poll_id)
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as UUID if not found
    if not poll:
        try:
            poll_uuid = UUID(poll_id)
            stmt = select(Poll).where(Poll.id == poll_uuid)
            result = await db.execute(stmt)
            poll = result.scalar_one_or_none()
        except ValueError:
            pass
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Return poll - candidates already have IDs from creation
    return {
        "id": str(poll.id),
        "short_id": poll.short_id,
        "title": poll.title,
        "description": poll.description,
        "candidates": poll.candidates,  # Has IDs from creation
        "settings": poll.settings,
        "status": get_poll_status(poll),
        "is_private": poll.is_private,
        "created_at": poll.created_at.isoformat() if poll.created_at else None,
        "closing_at": poll.closing_at.isoformat() if poll.closing_at else None
    }

@router.put("/{poll_id}")
async def update_poll(
    poll_id: str,
    poll_update: Dict[str, Any],
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Update poll - maintains candidate ID consistency"""
    
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
    
    # If updating candidates, ensure they have IDs
    if 'candidates' in poll_update:
        existing_ids = {c.get('id') for c in poll.candidates if isinstance(c, dict) and c.get('id')}
        updated_candidates = []
        next_index = len(poll.candidates)
        
        for idx, candidate in enumerate(poll_update['candidates']):
            if isinstance(candidate, dict):
                if candidate.get('id'):
                    # Has ID - keep it
                    updated_candidates.append(candidate)
                else:
                    # No ID - assign one
                    # Use next available index to avoid collisions
                    new_id = generate_candidate_id(next_index, False)
                    while new_id in existing_ids:
                        next_index += 1
                        new_id = generate_candidate_id(next_index, False)
                    
                    updated_candidates.append({
                        **candidate,
                        'id': new_id
                    })
                    existing_ids.add(new_id)
                    next_index += 1
            else:
                # String candidate - convert with new ID
                new_id = generate_candidate_id(next_index, False)
                while new_id in existing_ids:
                    next_index += 1
                    new_id = generate_candidate_id(next_index, False)
                
                updated_candidates.append({
                    'id': new_id,
                    'name': str(candidate),
                    'description': None
                })
                existing_ids.add(new_id)
                next_index += 1
        
        poll_update['candidates'] = updated_candidates
    
    # Update allowed fields
    for field in ['title', 'description', 'candidates', 'settings', 'status', 'closing_at']:
        if field in poll_update:
            setattr(poll, field, poll_update[field])
    
    poll.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(poll)
    
    return {"success": True, "message": "Poll updated", "candidates": poll.candidates}

@router.delete("/{poll_id}")
async def delete_poll(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Delete poll - admin only"""
    
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
    
    # Delete poll (cascades to ballots)
    await db.delete(poll)
    await db.commit()
    
    return {"success": True, "message": "Poll deleted"}

@router.post("/{poll_id}/close")
async def close_poll(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Close a poll - admin only"""
    
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
    
    # Close the poll
    poll.status = 'closed'
    poll.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {"success": True, "message": "Poll closed"}

@router.get("/{poll_id}/export")
async def export_poll_csv(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Export poll ballots as CSV (admin only)"""
    from fastapi.responses import Response
    
    # Find poll and verify admin
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
    
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Get ballots
    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    if not ballots:
        raise HTTPException(status_code=400, detail="No ballots to export")
    
    # Build candidate lookup including write-ins
    all_candidates = list(poll.candidates)
    candidate_ids = [c['id'] for c in poll.candidates if isinstance(c, dict)]
    candidate_names = {c['id']: c['name'] for c in poll.candidates if isinstance(c, dict)}
    
    # Add write-ins from ballots
    for ballot in ballots:
        if ballot.write_ins:
            for write_in in ballot.write_ins:
                if isinstance(write_in, dict):
                    wid = write_in.get('id')
                    wname = write_in.get('name')
                    if wid and wid not in candidate_ids:
                        candidate_ids.append(wid)
                        candidate_names[wid] = f"{wname} (write-in)"
    
    # Build CSV
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header row
    header = ["count"] + [candidate_names.get(cid, cid) for cid in candidate_ids]
    writer.writerow(header)
    
    # Aggregate identical ballots
    from collections import defaultdict
    ranking_patterns = defaultdict(int)
    
    for ballot in ballots:
        # Create a pattern key
        pattern = []
        for cid in candidate_ids:
            # Find rank for this candidate
            rank = None
            for r in ballot.rankings:
                if r.get('candidate_id') == cid:
                    rank = r.get('rank')
                    break
            pattern.append(rank if rank else "")
        
        pattern_key = tuple(pattern)
        ranking_patterns[pattern_key] += ballot.count
    
    # Write data rows
    for pattern, count in ranking_patterns.items():
        row = [count] + list(pattern)
        writer.writerow(row)
    
    # Return as CSV file
    csv_content = output.getvalue()
    filename = f"{poll.short_id}_export.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
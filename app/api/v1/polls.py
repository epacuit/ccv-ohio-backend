# app/api/v1/polls.py - FINAL VERSION WITH WRITE-IN SUPPORT
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
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
from app.models import Poll, Ballot, Voter

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
@limiter.limit("10/minute")
async def create_poll(
    request: Request,
    poll_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Create a new poll with properly structured candidates and voters"""
    
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
        # Allow slugs for test polls without restriction
        # For production polls, check if owner is in allowed list
        if not poll_data.get('is_test', False):
            allowed_emails_json = os.getenv("SLUG_ALLOWED_EMAILS", "[]")
            allowed_emails = json.loads(allowed_emails_json)
            
            # Only restrict slugs if SLUG_ALLOWED_EMAILS is explicitly configured
            if allowed_emails and poll_data.get('owner_email') not in allowed_emails:
                slug = None
        
        # Check if slug is already taken (for both test and non-test polls)
        if slug:
            stmt = select(Poll).where(Poll.slug == slug)
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"Slug '{slug}' is already taken. Please choose a different one."
                )
    
    # CRITICAL: Ensure all candidates have IDs before storing
    candidates_with_ids = ensure_candidates_have_ids(poll_data.get('candidates', []))
    
    # Extract voter emails BEFORE creating the poll
    voter_emails = poll_data.pop('voter_emails', [])
    
    # Create poll
    poll = Poll(
        short_id=short_id,
        slug=slug,
        title=poll_data['title'],
        description=poll_data.get('description'),
        candidates=candidates_with_ids,
        settings=poll_data.get('settings', {}),
        is_private=poll_data.get('is_private', False),
        is_test=poll_data.get('is_test', False),
        status='open',
        closing_at=poll_data.get('closing_at'),
        owner_email=poll_data.get('owner_email'),
        admin_token=secrets.token_urlsafe(32),
        password_hash=poll_data.get('password_hash')
    )
    
    db.add(poll)
    await db.commit()
    await db.refresh(poll)
    
    # ADD VOTERS FOR PRIVATE POLLS
    voters_added = 0
    if poll.is_private and voter_emails:
        import hashlib
        from datetime import datetime, timezone
        
        for email in voter_emails:
            email = email.lower().strip()
            
            # Check if voter already exists (shouldn't happen on creation, but just in case)
            stmt = select(Voter).where(
                Voter.poll_id == poll.id,
                Voter.email == email
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                # Create voter
                voter = Voter(
                    poll_id=poll.id,
                    email=email,
                    email_hash=hashlib.sha256(email.encode()).hexdigest(),
                    token=secrets.token_urlsafe(32),
                    invitation_sent=False,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(voter)
                voters_added += 1
        
        await db.commit()
        print(f"✅ Added {voters_added} voters to private poll {poll.short_id}")
    
    # Return with candidates and voter count
    return {
        "id": str(poll.id),
        "short_id": poll.short_id,
        "slug": poll.slug,
        "title": poll.title,  # Include title for success page
        "admin_token": poll.admin_token,
        "url": f"{BASE_URL}/p/{poll.short_id}",
        "qr_code": f"{BASE_URL}/qr/{poll.short_id}.png",
        "candidates": poll.candidates,
        "voters_added": voters_added  # Include count of voters added
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
            "slug": p.slug,
            "title": p.title,
            "status": get_poll_status(p),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "total_ballots": int(total_ballots),
            "admin_token": p.admin_token  # ADD THIS LINE
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
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Return poll - candidates already have IDs from creation
    return {
        "id": str(poll.id),
        "short_id": poll.short_id,
        "slug": poll.slug,
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
    """Update poll - maintains candidate ID consistency and prevents illegal changes"""
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Check if poll has votes
    stmt = select(func.count(Ballot.id)).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballot_count = result.scalar_one()
    
    # If updating candidates and votes exist, validate no additions/removals
    if 'candidates' in poll_update and ballot_count > 0:
        existing_ids = {c.get('id') for c in poll.candidates if isinstance(c, dict) and c.get('id')}
        new_ids = {c.get('id') for c in poll_update['candidates'] if isinstance(c, dict) and c.get('id')}
        
        # Check if any candidates were added or removed
        if existing_ids != new_ids:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot add or remove candidates after voting has started. This poll has {ballot_count} votes."
            )
        
        # Ensure the order and count remains the same
        if len(poll.candidates) != len(poll_update['candidates']):
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot change the number of candidates after voting has started. This poll has {ballot_count} votes."
            )
        
        # Allow name/description updates but keep the same IDs
        updated_candidates = []
        for orig_candidate in poll.candidates:
            # Find the corresponding candidate in the update
            matching_update = None
            for upd_candidate in poll_update['candidates']:
                if upd_candidate.get('id') == orig_candidate.get('id'):
                    matching_update = upd_candidate
                    break
            
            if matching_update:
                # Update name/description but keep the original ID
                updated_candidates.append({
                    'id': orig_candidate['id'],  # Keep original ID
                    'name': matching_update.get('name', orig_candidate.get('name')),
                    'description': matching_update.get('description', orig_candidate.get('description')),
                    'image_url': matching_update.get('image_url', orig_candidate.get('image_url'))
                })
            else:
                # Keep original if no matching update found
                updated_candidates.append(orig_candidate)
        
        poll_update['candidates'] = updated_candidates
        
    elif 'candidates' in poll_update and ballot_count == 0:
        # No votes yet, ensure candidates have IDs
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
    
    return {
        "success": True, 
        "message": "Poll updated", 
        "candidates": poll.candidates,
        "has_votes": ballot_count > 0
    }

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
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
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
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
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

# Add these endpoints to your existing polls.py file after the close_poll endpoint

@router.post("/{poll_id}/toggle-status")
async def toggle_poll_status(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Toggle poll open/closed status - admin only"""
    from datetime import datetime, timezone
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Toggle status
    new_status = 'closed' if poll.status == 'open' else 'open'
    poll.status = new_status
    poll.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {"success": True, "status": new_status, "message": f"Poll {new_status}"}

@router.get("/{poll_id}/statistics")
async def get_poll_statistics(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed poll statistics - admin only"""
    from datetime import datetime, timezone, timedelta
    
    # Find poll and verify admin
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Get ballot statistics
    stmt = select(
        func.count(Ballot.id).label('unique_voters'),
        func.sum(Ballot.count).label('total_ballots'),
        func.max(Ballot.updated_at).label('last_vote_time'),
        func.min(Ballot.submitted_at).label('first_vote_time')
    ).where(Ballot.poll_id == poll.id)
    
    result = await db.execute(stmt)
    stats = result.one()
    
    # Calculate voting rate
    voting_rate = 0
    if stats.first_vote_time and stats.last_vote_time and stats.unique_voters > 0:
        time_span = (stats.last_vote_time - stats.first_vote_time).total_seconds() / 3600
        if time_span > 0:
            voting_rate = stats.unique_voters / time_span
    
    return {
        "total_votes": int(stats.total_ballots) if stats.total_ballots else 0,
        "unique_voters": int(stats.unique_voters) if stats.unique_voters else 0,
        "last_vote_time": stats.last_vote_time.isoformat() if stats.last_vote_time else None,
        "first_vote_time": stats.first_vote_time.isoformat() if stats.first_vote_time else None,
        "voting_rate": round(voting_rate, 2),
        "poll_status": get_poll_status(poll),
    }

@router.post("/authenticate-admin")
async def authenticate_admin(
    auth_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Authenticate admin with password or token"""
    poll_id = auth_data.get('poll_id')
    admin_token = auth_data.get('admin_token')
    password = auth_data.get('password')
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Check authentication
    authenticated = False
    auth_method = None
    
    if admin_token and poll.admin_token == admin_token:
        authenticated = True
        auth_method = "token"
    elif password and poll.password_hash:
        # You would need to implement password hashing/checking here
        # For now, simple comparison (you should use bcrypt or similar in production)
        if poll.password_hash == password:  # This should be proper hash comparison
            authenticated = True
            auth_method = "password"
    
    if not authenticated:
        raise HTTPException(status_code=403, detail="Invalid credentials")
    
    return {
        "authenticated": True,
        "auth_method": auth_method,
        "admin_token": poll.admin_token  # Return token for future requests
    }
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
    
    # Try as slug if not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
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
    
    # Build pairwise CSV (matches bulk-import format)
    import csv
    from io import StringIO

    candidates = poll.candidates or []
    cand_name_by_id = {}
    for c in candidates:
        if isinstance(c, dict):
            cand_name_by_id[c.get('id', '')] = c.get('name', 'Unknown')

    # Generate matchup columns (N choose 2)
    matchup_columns = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            c1 = candidates[i]
            c2 = candidates[j]
            c1_id = c1.get('id', '') if isinstance(c1, dict) else str(i)
            c2_id = c2.get('id', '') if isinstance(c2, dict) else str(j)
            c1_name = c1.get('name', f'Candidate {i}') if isinstance(c1, dict) else str(c1)
            c2_name = c2.get('name', f'Candidate {j}') if isinstance(c2, dict) else str(c2)
            matchup_columns.append({
                'header': f'{c1_name} vs {c2_name}',
                'cand1_id': c1_id,
                'cand2_id': c2_id,
                'cand1_name': c1_name,
                'cand2_name': c2_name,
            })

    output = StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['Count'] + [m['header'] for m in matchup_columns])

    # Aggregate identical ballot patterns
    from collections import defaultdict
    ballot_patterns = defaultdict(int)

    for ballot in ballots:
        choice_lookup = {}
        for choice in (ballot.pairwise_choices or []):
            key = (choice.get('cand1_id', ''), choice.get('cand2_id', ''))
            choice_lookup[key] = choice.get('choice', '')

        pattern = []
        for m in matchup_columns:
            choice_val = choice_lookup.get((m['cand1_id'], m['cand2_id']), '')
            if choice_val == 'cand1':
                pattern.append(m['cand1_name'])
            elif choice_val == 'cand2':
                pattern.append(m['cand2_name'])
            elif choice_val == 'tie':
                pattern.append('both')
            else:
                pattern.append('')

        ballot_patterns[tuple(pattern)] += ballot.count

    # Write data rows
    for pattern, count in ballot_patterns.items():
        writer.writerow([count] + list(pattern))
    
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

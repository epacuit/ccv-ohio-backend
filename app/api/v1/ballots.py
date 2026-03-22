# app/api/v1/ballots.py - WITH CACHE INVALIDATION, TOKEN SUPPORT, AND GET BALLOT
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Dict, Any, List
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from datetime import datetime, timezone
from uuid import UUID, uuid4
import hashlib
import os

from app.db import get_db
from app.models import Ballot, Poll, Result, Voter

router = APIRouter()

# Development mode - auto-generate fingerprints for testing
DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'

async def invalidate_results_cache(poll_id: UUID, db: AsyncSession):
    """Mark cached results as stale when new ballots are submitted"""
    stmt = update(Result).where(
        Result.poll_id == poll_id,
        Result.is_current == True
    ).values(is_current=False)
    await db.execute(stmt)

def hash_fingerprint(fingerprint: str) -> str:
    """Hash fingerprint for privacy"""
    return hashlib.sha256(fingerprint.encode()).hexdigest() if fingerprint else None

def hash_ip(ip_address: str) -> str:
    """Hash IP for privacy"""
    return hashlib.sha256(ip_address.encode()).hexdigest() if ip_address else None

def ensure_write_ins_have_ids(write_ins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure all write-in candidates have unique IDs.
    Write-ins use format: write-in-{uuid} to avoid collisions with regular candidates.
    """
    processed_write_ins = []
    
    for write_in in write_ins:
        if isinstance(write_in, dict):
            if write_in.get('id'):
                # Already has an ID
                processed_write_ins.append(write_in)
            else:
                # Generate a unique write-in ID
                processed_write_ins.append({
                    **write_in,
                    'id': f"write-in-{uuid4().hex[:8]}",
                    'is_write_in': True
                })
        elif isinstance(write_in, str):
            # String write-in - convert to dict with ID
            processed_write_ins.append({
                'id': f"write-in-{uuid4().hex[:8]}",
                'name': write_in,
                'is_write_in': True
            })
    
    return processed_write_ins

# ==============================================================================
# GET BALLOT - Retrieve existing ballot for voter
# ==============================================================================

@router.get("/{poll_id}/ballot")
async def get_voter_ballot(
    poll_id: str,
    voter_fingerprint: str = Query(None),
    voter_token: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a voter's existing ballot for pre-populating the voting form.
    
    Returns 404 if:
    - Poll not found
    - Voter hasn't voted yet
    
    For public polls: uses voter_fingerprint
    For private polls: uses voter_token
    
    Args:
        poll_id: Poll identifier (UUID, short_id, or slug)
        voter_fingerprint: Unique voter identifier for public polls
        voter_token: Voter token for private polls
    
    Returns:
        {
            "has_voted": True,
            "ballot": {
                "ballot_id": "...",
                "pairwise_choices": [...],
                "updated_at": "..."
            }
        }
    """
    # Find poll using same logic as submit_ballot
    poll = None
    
    if isinstance(poll_id, str):
        # Try as short_id first
        stmt = select(Poll).where(Poll.short_id == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
        
        # If not found, try as UUID
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
    
    # Find ballot
    ballot = None
    
    if poll.is_private and voter_token:
        # Private poll - find by token
        stmt = select(Ballot).where(
            Ballot.poll_id == poll.id,
            Ballot.voter_token == voter_token
        )
        result = await db.execute(stmt)
        ballot = result.scalar_one_or_none()
    elif voter_fingerprint:
        # Public poll - find by hashed fingerprint
        fingerprint_hash = hash_fingerprint(voter_fingerprint)
        stmt = select(Ballot).where(
            Ballot.poll_id == poll.id,
            Ballot.voter_fingerprint == fingerprint_hash
        )
        result = await db.execute(stmt)
        ballot = result.scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=400, 
            detail="Must provide voter_fingerprint or voter_token"
        )
    
    if not ballot:
        raise HTTPException(status_code=404, detail="No ballot found for this voter")
    
    return {
        "has_voted": True,
        "ballot": {
            "ballot_id": str(ballot.id),
            "pairwise_choices": ballot.pairwise_choices,
            "updated_at": ballot.updated_at.isoformat() if ballot.updated_at else None
        }
    }

# ==============================================================================
# SUBMIT/UPDATE BALLOT
# ==============================================================================

@router.post("/")
@limiter.limit("20/minute")
async def submit_ballot(
    request: Request,
    ballot_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Submit or update a ballot"""
    
    # Parse poll_id - handle both short_id and UUID
    poll_id_input = ballot_data.get('poll_id')
    poll = None
    
    # First try to find poll by short_id or UUID
    if isinstance(poll_id_input, str):
        # Try as short_id first
        stmt = select(Poll).where(Poll.short_id == poll_id_input)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
        
        # If not found, try as UUID
        if not poll:
            try:
                poll_uuid = UUID(poll_id_input)
                stmt = select(Poll).where(Poll.id == poll_uuid)
                result = await db.execute(stmt)
                poll = result.scalar_one_or_none()
            except ValueError:
                pass
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id_input)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Use the actual poll UUID for all operations
    poll_id = poll.id
    
    # ========== VALIDATION: Poll Status and Deadline ==========
    # Check if poll is closed
    if poll.status == 'closed':
        raise HTTPException(status_code=400, detail="Poll is closed")
    
    if poll.closing_at and poll.closing_at < datetime.now(timezone.utc):
        # Poll should be closed but status not updated
        poll.status = 'closed'
        await db.commit()
        raise HTTPException(status_code=400, detail="Poll voting deadline has passed")
    
    # ========== VALIDATION: Ballot Data ==========
    pairwise_choices = ballot_data.get('pairwise_choices', [])

    # Get valid candidate IDs from poll
    valid_candidate_ids = {c['id'] for c in poll.candidates}

    if not pairwise_choices:
        raise HTTPException(status_code=400, detail="No pairwise choices provided")

    # Validate pairwise choices
    seen_pairs = set()
    for choice in pairwise_choices:
        cand1_id = choice.get('cand1_id')
        cand2_id = choice.get('cand2_id')
        choice_val = choice.get('choice')

        if not cand1_id or not cand2_id:
            raise HTTPException(status_code=400, detail="Each pairwise choice must have cand1_id and cand2_id")

        if cand1_id not in valid_candidate_ids:
            raise HTTPException(status_code=400, detail=f"Invalid candidate ID: {cand1_id}")
        if cand2_id not in valid_candidate_ids:
            raise HTTPException(status_code=400, detail=f"Invalid candidate ID: {cand2_id}")

        if choice_val not in ('cand1', 'cand2', 'tie', 'neither'):
            raise HTTPException(status_code=400, detail=f"Invalid choice value: {choice_val}. Must be 'cand1', 'cand2', 'tie', or 'neither'")

        # Check for duplicate pairs
        pair_key = frozenset([cand1_id, cand2_id])
        if pair_key in seen_pairs:
            raise HTTPException(status_code=400, detail=f"Duplicate matchup for {cand1_id} vs {cand2_id}")
        seen_pairs.add(pair_key)

    # Check require_all_matchups setting
    if poll.settings.get('require_all_matchups', False):
        num_candidates = len(poll.candidates)
        expected_matchups = (num_candidates * (num_candidates - 1)) // 2
        if len(pairwise_choices) < expected_matchups:
            raise HTTPException(
                status_code=400,
                detail=f"Must complete all {expected_matchups} matchups"
            )
    
    # Extract voter token
    voter_token = ballot_data.get('voter_token')
    
    # For private polls, validate token
    if poll.is_private:
        if not voter_token:
            raise HTTPException(status_code=403, detail="Voting token required for private poll")
        
        # Check if token is valid in Voter table
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.token == voter_token
        )
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if not voter:
            raise HTTPException(status_code=403, detail="Invalid voting token")
    
    # Hash sensitive data
    # Dev mode: auto-generate fingerprint if not provided
    fp_input = ballot_data.get('voter_fingerprint')
    if DEV_MODE and not fp_input:
        fp_input = f'dev-{uuid4().hex[:8]}'
        print(f"🧪 DEV MODE: Auto-generated fingerprint: {fp_input}")
    
    voter_fingerprint = hash_fingerprint(fp_input)
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
        # Note: If ballot exists, we'll update it below (not error)
            
    elif voter_fingerprint:
        # Public poll - check by fingerprint
        stmt = select(Ballot).where(
            Ballot.poll_id == poll_id,
            Ballot.voter_fingerprint == voter_fingerprint
        )
        result = await db.execute(stmt)
        existing_ballot = result.scalar_one_or_none()
    
    if existing_ballot:
        # Check if vote updates are allowed for this poll
        if not poll.settings.get('allow_vote_updates', True):
            raise HTTPException(
                status_code=400, 
                detail="Vote updates are not allowed for this poll. Your original vote has been recorded."
            )
        
        # Update existing ballot (for both public and private polls)
        existing_ballot.pairwise_choices = pairwise_choices
        existing_ballot.write_ins = []
        existing_ballot.updated_at = datetime.now(timezone.utc)
        existing_ballot.ip_hash = ip_hash
        
        await db.commit()
        await db.refresh(existing_ballot)
        
        # INVALIDATE CACHED RESULTS
        await invalidate_results_cache(poll.id, db)
        await db.commit()
        
        return {
            "success": True,
            "message": "Vote updated",
            "ballot_id": str(existing_ballot.id),
            "ballot_data": {
                "pairwise_choices": existing_ballot.pairwise_choices,
            }
        }
    else:
        # Create new ballot
        ballot = Ballot(
            poll_id=poll_id,
            pairwise_choices=pairwise_choices,
            write_ins=[],
            count=ballot_data.get('count', 1),
            voter_fingerprint=voter_fingerprint,
            voter_token=voter_token,
            ip_hash=ip_hash,
            import_batch_id=ballot_data.get('import_batch_id'),
            is_test=ballot_data.get('is_test', False)
        )
        
        db.add(ballot)
        await db.commit()
        await db.refresh(ballot)
        
        # INVALIDATE CACHED RESULTS
        await invalidate_results_cache(poll.id, db)
        await db.commit()
        
        return {
            "success": True,
            "message": "Vote recorded",
            "ballot_id": str(ballot.id),
            "ballot_data": {
                "pairwise_choices": ballot.pairwise_choices,
            }
        }

@router.get("/check")
async def check_existing_ballot(
    poll_id: str = Query(...),
    voter_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Check if a voter token has already been used to vote in a private poll"""
    
    # Find the poll
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
    
    # For private polls, verify the token is valid
    if poll.is_private:
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.token == voter_token
        )
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if not voter:
            raise HTTPException(status_code=403, detail="Invalid voting token")
    
    # Check if this token has voted
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.voter_token == voter_token
    )
    result = await db.execute(stmt)
    ballot = result.scalar_one_or_none()
    
    if ballot:
        # Return the ballot data
        return {
            "has_voted": True,
            "ballot": {
                "id": str(ballot.id),
                "submitted_at": ballot.submitted_at.isoformat() if ballot.submitted_at else None,
                "pairwise_choices": ballot.pairwise_choices,
                "write_ins": ballot.write_ins if ballot.write_ins else []
            }
        }
    else:
        return {
            "has_voted": False,
            "ballot": None
        }

@router.get("/poll/{poll_id}/public")
async def get_poll_ballots_public(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all ballots for a poll - public, anonymized (choices and counts only)"""

    poll = None
    if isinstance(poll_id, str):
        stmt = select(Poll).where(Poll.short_id == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()

        if not poll:
            try:
                poll_uuid = UUID(poll_id)
                stmt = select(Poll).where(Poll.id == poll_uuid)
                result = await db.execute(stmt)
                poll = result.scalar_one_or_none()
            except ValueError:
                pass

    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")

    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()

    return [
        {
            "pairwise_choices": b.pairwise_choices,
            "count": b.count,
        }
        for b in ballots
    ]


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
    
    # Get all ballots
    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    # Return with write-ins included
    return [
        {
            "id": str(b.id),
            "pairwise_choices": b.pairwise_choices,
            "write_ins": b.write_ins,
            "count": b.count,
            "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            "is_test": b.is_test
        }
        for b in ballots
    ]

@router.get("/{ballot_id}/pdf")
async def get_ballot_pdf(
    ballot_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Generate and return PDF of ballot with proper candidate/write-in handling"""
    from fastapi.responses import Response
    
    # Get ballot
    try:
        ballot_uuid = UUID(ballot_id)
        stmt = select(Ballot).where(Ballot.id == ballot_uuid)
        result = await db.execute(stmt)
        ballot = result.scalar_one_or_none()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ballot ID")
    
    if not ballot:
        raise HTTPException(status_code=404, detail="Ballot not found")
    
    # Get poll for candidate names
    stmt = select(Poll).where(Poll.id == ballot.poll_id)
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Generate PDF - the generator now handles IDs properly
    from app.services.pdf_generator import generate_ballot_pdf
    pdf_content = generate_ballot_pdf(ballot, poll)
    
    # Return PDF
    filename = f"ballot_{poll.short_id}_{ballot.submitted_at.strftime('%Y%m%d')}.pdf"
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(pdf_content))
        }
    )

@router.post("/bulk-import")
async def bulk_import_ballots(
    import_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Bulk import ballots from CSV - with proper ID handling"""
    
    poll_id = import_data.get('poll_id')
    admin_token = import_data.get('admin_token')
    ballots_data = import_data.get('ballots', [])
    
    if isinstance(poll_id, str):
        try:
            poll_id = UUID(poll_id)
        except ValueError:
            # Try to find by short_id
            stmt = select(Poll).where(Poll.short_id == poll_id)
            result = await db.execute(stmt)
            poll = result.scalar_one_or_none()
            if poll:
                poll_id = poll.id
            else:
                raise HTTPException(status_code=404, detail="Poll not found")
    
    # Get poll and verify admin
    stmt = select(Poll).where(Poll.id == poll_id)
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Aggregate identical ballots for efficiency
    from collections import defaultdict
    ballot_counts = defaultdict(int)

    for ballot in ballots_data:
        # Create hashable key from pairwise choices
        choices_key = tuple(
            (c['cand1_id'], c['cand2_id'], c['choice'])
            for c in sorted(ballot.get('pairwise_choices', []),
                          key=lambda x: (x['cand1_id'], x['cand2_id']))
        )

        count = ballot.get('count', 1)
        ballot_counts[choices_key] += count

    # Create ballot records
    import_batch_id = f"import_{poll_id}_{datetime.now(timezone.utc).isoformat()}"
    created_count = 0
    total_votes = 0

    for choices_tuple, count in ballot_counts.items():
        pairwise_choices = [
            {"cand1_id": c1, "cand2_id": c2, "choice": ch}
            for c1, c2, ch in choices_tuple
        ]

        ballot = Ballot(
            poll_id=poll_id,
            pairwise_choices=pairwise_choices,
            write_ins=[],
            count=count,
            import_batch_id=import_batch_id,
            is_test=False
        )

        db.add(ballot)
        created_count += 1
        total_votes += count

    await db.commit()

    # INVALIDATE CACHED RESULTS AFTER BULK IMPORT
    await invalidate_results_cache(poll_id, db)
    await db.commit()

    return {
        "success": True,
        "message": f"Imported {total_votes} votes in {created_count} ballot records",
        "import_batch_id": import_batch_id,
        "unique_patterns": created_count,
        "total_votes": total_votes,
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
    
    # Delete all ballots for this poll
    stmt = select(Ballot).where(Ballot.poll_id == poll.id)
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    count = len(ballots)
    for ballot in ballots:
        await db.delete(ballot)
    
    await db.commit()
    
    # INVALIDATE CACHED RESULTS AFTER CLEARING
    await invalidate_results_cache(poll.id, db)
    await db.commit()
    
    return {
        "success": True,
        "message": f"Deleted {count} ballot records"
    }
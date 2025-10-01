# app/api/v1/ballots.py - WITH CACHE INVALIDATION AND TOKEN SUPPORT
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID, uuid4
import hashlib

from app.db import get_db
from app.models import Ballot, Poll, Result, Voter

router = APIRouter()

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

@router.post("/")
async def submit_ballot(
    ballot_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Submit or update a ballot with proper ID handling for write-ins"""
    
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
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Use the actual poll UUID for all operations
    poll_id = poll.id
    
    # Check if poll is open
    if poll.status == 'closed':
        return {"success": False, "message": "Poll is closed"}
    
    if poll.closing_at and poll.closing_at < datetime.now(timezone.utc):
        # Poll should be closed but status not updated
        poll.status = 'closed'
        await db.commit()
        return {"success": False, "message": "Poll is closed"}
    
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
    
    # CRITICAL: Ensure write-ins have proper IDs
    write_ins = ballot_data.get('write_ins', [])
    if write_ins:
        write_ins = ensure_write_ins_have_ids(write_ins)
        
        # Validate write-ins don't conflict with poll candidates
        from app.services.ballot_process_rules import normalize_candidate_name, find_candidate_matches
        
        for write_in in write_ins:
            matches = find_candidate_matches(write_in['name'], poll.candidates)
            if matches:
                return {
                    "success": False, 
                    "message": f"Write-in '{write_in['name']}' conflicts with existing candidate '{matches[0]['name']}'"
                }
    
    # Hash sensitive data
    voter_fingerprint = hash_fingerprint(ballot_data.get('voter_fingerprint'))
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
        
        if existing_ballot:
            raise HTTPException(status_code=400, detail="This token has already been used to vote")
            
    elif voter_fingerprint:
        # Public poll - check by fingerprint
        stmt = select(Ballot).where(
            Ballot.poll_id == poll_id,
            Ballot.voter_fingerprint == voter_fingerprint
        )
        result = await db.execute(stmt)
        existing_ballot = result.scalar_one_or_none()
    
    if existing_ballot and not poll.is_private:
        # Update existing ballot (only for public polls)
        existing_ballot.rankings = ballot_data['rankings']
        existing_ballot.write_ins = write_ins  # Now with proper IDs
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
                "rankings": existing_ballot.rankings,
                "write_ins": existing_ballot.write_ins
            }
        }
    else:
        # Create new ballot
        ballot = Ballot(
            poll_id=poll_id,
            rankings=ballot_data['rankings'],
            write_ins=write_ins,  # Now with proper IDs
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
                "rankings": ballot.rankings,
                "write_ins": ballot.write_ins
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
                "rankings": ballot.rankings,
                "write_ins": ballot.write_ins if ballot.write_ins else []
            }
        }
    else:
        return {
            "has_voted": False,
            "ballot": None
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
            "rankings": b.rankings,
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
    
    # Process write-ins in imported ballots
    for ballot_data in ballots_data:
        if ballot_data.get('write_ins'):
            ballot_data['write_ins'] = ensure_write_ins_have_ids(ballot_data['write_ins'])
    
    # Detect maximum rank in imported data
    max_rank_found = 0
    rank_4_count = 0
    for ballot_data in ballots_data:
        ballot_max = 0
        for ranking in ballot_data.get('rankings', []):
            rank = ranking.get('rank', 0)
            max_rank_found = max(max_rank_found, rank)
            ballot_max = max(ballot_max, rank)
        if ballot_max == 4:
            rank_4_count += ballot_data.get('count', 1)
    
    # Log what we found
    print(f"\n📊 IMPORT STATISTICS for poll {poll.short_id}:")
    print(f"   - Total ballot patterns: {len(ballots_data)}")
    print(f"   - Maximum rank found: {max_rank_found}")
    print(f"   - Ballots with rank 4: {rank_4_count} votes")
    print(f"   - Poll has {len(poll.candidates)} candidates")
    
    # ALWAYS update poll's num_ranks based on the data
    # The poll should display at least as many columns as the highest rank found
    num_ranks_needed = max(max_rank_found, len(poll.candidates))
    current_num_ranks = poll.settings.get('num_ranks') if poll.settings else None
    
    # Update if needed
    if current_num_ranks != num_ranks_needed:
        if not poll.settings:
            poll.settings = {}
        poll.settings['num_ranks'] = num_ranks_needed
        poll.updated_at = datetime.now(timezone.utc)
        
        print(f"\n✅ POLL {poll.short_id} RANK CONFIGURATION:")
        print(f"   - Max rank in imported data: {max_rank_found}")
        print(f"   - Number of candidates: {len(poll.candidates)}")
        print(f"   - Setting num_ranks = {num_ranks_needed} (was {current_num_ranks})")
        if max_rank_found > len(poll.candidates):
            print(f"   - ⚠️ Alaska 2022 scenario detected: rank {max_rank_found} for {len(poll.candidates)} candidates")
            print(f"   - Frontend will display {num_ranks_needed} columns to show all votes")
        
        await db.commit()
        await db.refresh(poll)
    
    # Aggregate identical ballots for efficiency
    from collections import defaultdict
    ranking_counts = defaultdict(int)
    
    for ballot in ballots_data:
        # Create hashable key from rankings and write-ins
        ranking_key = tuple(
            (r['candidate_id'], r['rank']) 
            for r in sorted(ballot['rankings'], key=lambda x: (x['rank'], x['candidate_id']))
        )
        
        # Include write-ins in the key
        write_in_key = tuple(
            (w['id'], w['name']) 
            for w in sorted(ballot.get('write_ins', []), key=lambda x: x.get('id', ''))
        ) if ballot.get('write_ins') else ()
        
        full_key = (ranking_key, write_in_key)
        count = ballot.get('count', 1)
        ranking_counts[full_key] += count
    
    # Create ballot records
    import_batch_id = f"import_{poll_id}_{datetime.now(timezone.utc).isoformat()}"
    created_count = 0
    total_votes = 0
    
    for (ranking_tuple, write_in_tuple), count in ranking_counts.items():
        # Convert back to rankings format
        rankings = [
            {"candidate_id": cid, "rank": rank}
            for cid, rank in ranking_tuple
        ]
        
        # Convert back to write-ins format
        write_ins = [
            {"id": wid, "name": wname, "is_write_in": True}
            for wid, wname in write_in_tuple
        ] if write_in_tuple else []
        
        ballot = Ballot(
            poll_id=poll_id,
            rankings=rankings,
            write_ins=write_ins,
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
    
    # Get the updated poll's num_ranks for confirmation
    final_num_ranks = poll.settings.get('num_ranks') if poll.settings else len(poll.candidates)
    
    return {
        "success": True,
        "message": f"Imported {total_votes} votes in {created_count} ballot records",
        "import_batch_id": import_batch_id,
        "unique_patterns": created_count,
        "total_votes": total_votes,
        "poll_num_ranks": final_num_ranks,
        "max_rank_found": max_rank_found,
        "num_candidates": len(poll.candidates),
        "note": f"Poll will display {final_num_ranks} ranking columns"
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
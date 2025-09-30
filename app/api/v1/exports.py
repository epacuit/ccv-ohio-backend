# app/api/v1/exports.py
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
import csv
from io import StringIO, BytesIO

from app.db import get_db
from app.models import Poll, Ballot, Result
from app.services.results_pdf_generator import generate_results_pdf
from app.services.voting_calculation import calculate_mwsl_with_explanation

router = APIRouter()

@router.get("/poll/{poll_id}/results-pdf")
async def download_results_pdf(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Download poll results as PDF."""
    
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
    
    # Get latest results
    stmt = select(Result).where(
        Result.poll_id == poll.id,
        Result.is_current == True
    )
    result = await db.execute(stmt)
    results_record = result.scalar_one_or_none()
    
    if not results_record:
        # Generate results if not cached
        stmt = select(Ballot).where(
            Ballot.poll_id == poll.id,
            Ballot.is_test == False
        )
        result = await db.execute(stmt)
        ballots = result.scalars().all()
        
        if not ballots:
            raise HTTPException(status_code=400, detail="No ballots found")
        
        # Use the voting_calculation module
        results_data = calculate_mwsl_with_explanation(ballots, poll.candidates)
    else:
        results_data = results_record.data  # Changed from result_data to data
    
    # Generate PDF
    poll_dict = {
        'id': str(poll.id),
        'short_id': poll.short_id,
        'title': poll.title,
        'description': poll.description,
        'candidates': poll.candidates
    }
    
    try:
        pdf_content = generate_results_pdf(poll_dict, results_data)
        
        filename = f"results_{poll.short_id}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


@router.get("/poll/{poll_id}/ballots-csv")
async def download_ballots_csv(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Download all ballots as CSV."""
    
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
    
    # Get all ballots
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.is_test == False
    )
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    if not ballots:
        raise HTTPException(status_code=400, detail="No ballots found")
    
    # Build CSV
    output = StringIO()
    
    # Get candidate names
    candidate_names = ['count']  # First column is always count
    candidate_ids = []
    
    for candidate in poll.candidates:
        if isinstance(candidate, dict):
            name = candidate.get('name', f'Candidate {len(candidate_names)}')
            cid = candidate.get('id', f'candidate-{len(candidate_ids)}')
        else:
            name = str(candidate)
            cid = f'candidate-{len(candidate_ids)}'
        candidate_names.append(name)
        candidate_ids.append(cid)
    
    # Check for write-ins across all ballots
    all_write_ins = {}
    for ballot in ballots:
        if ballot.write_ins:
            for write_in in ballot.write_ins:
                wid = write_in.get('id')
                wname = write_in.get('name')
                if wid and wname and wid not in all_write_ins:
                    all_write_ins[wid] = wname
    
    # Add write-ins to header
    for wid, wname in all_write_ins.items():
        candidate_names.append(f"{wname} (write-in)")
        candidate_ids.append(wid)
    
    # Write CSV
    writer = csv.writer(output)
    
    # Header row
    writer.writerow(candidate_names)
    
    # Process each ballot
    for ballot in ballots:
        row = [ballot.count]  # Start with count
        
        # Build rank lookup for this ballot
        rank_lookup = {}
        for ranking in ballot.rankings:
            cid = ranking.get('candidate_id')
            rank = ranking.get('rank')
            if cid and rank is not None:
                rank_lookup[str(cid)] = rank
        
        # Add rank for each candidate
        for cid in candidate_ids:
            rank = rank_lookup.get(str(cid), '')  # Empty if not ranked
            row.append(rank)
        
        writer.writerow(row)
    
    # Get CSV content
    csv_content = output.getvalue()
    output.close()
    
    filename = f"ballots_{poll.short_id}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
# app/api/v1/exports.py
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
import csv
import os
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
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
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
        # Get base URL from environment variable
        base_url = os.getenv('BASE_URL', 'https://betterchoices.vote')
        pdf_content = generate_results_pdf(poll_dict, results_data, base_url=base_url)
        
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
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
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
    
    # Build CSV in pairwise format (matches bulk-import format)
    output = StringIO()

    # Build candidate lookup
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

    # Write CSV
    writer = csv.writer(output)

    # Header row
    writer.writerow(['Count'] + [m['header'] for m in matchup_columns])

    # Process each ballot
    for ballot in ballots:
        row = [ballot.count]

        # Build choice lookup for this ballot
        choice_lookup = {}
        for choice in (ballot.pairwise_choices or []):
            key = (choice.get('cand1_id', ''), choice.get('cand2_id', ''))
            choice_lookup[key] = choice.get('choice', '')

        # Add cell for each matchup
        for m in matchup_columns:
            choice_val = choice_lookup.get((m['cand1_id'], m['cand2_id']), '')

            if choice_val == 'cand1':
                row.append(m['cand1_name'])
            elif choice_val == 'cand2':
                row.append(m['cand2_name'])
            elif choice_val == 'tie':
                row.append('both')
            else:
                row.append('')  # neither or missing

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
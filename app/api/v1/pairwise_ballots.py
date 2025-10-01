# app/api/v1/pairwise_ballots.py
"""
Pairwise ballot comparison endpoints with built-in optimization.
Single source of truth - handles both small and large polls efficiently.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from collections import defaultdict

from app.db import get_db
from app.models import Ballot, Poll
from app.services.ballot_process_rules import (
    infer_pairwise_comparison_from_ballot_alaska_rules,
    normalize_candidate_name
)

router = APIRouter()


def process_ballot_for_comparison(
    ballot_rankings: List[Dict], 
    cand1_id: str, 
    cand2_id: str,
    write_ins: Optional[List[Dict]] = None
) -> str:
    """
    Process a single ballot to determine the pairwise comparison result.
    Returns: 'cand1_wins', 'cand2_wins', 'tie', or 'undefined'
    """
    ranking_dict = {}
    for ranking in ballot_rankings:
        ranking_dict[ranking['candidate_id']] = ranking['rank']
    
    # DEBUG LOGGING TO FIND THE BUG
    # Assuming candidate-0 = Peltola, candidate-1 = Palin, candidate-2 = Begich
    if (cand1_id == 'candidate-2' and cand2_id == 'candidate-1') or \
       (cand1_id == 'candidate-1' and cand2_id == 'candidate-2'):
        # This is Begich vs Palin comparison
        print(f"\n=== BEGICH vs PALIN DEBUG ===")
        print(f"Ballot rankings input: {ballot_rankings}")
        print(f"Ranking dict built: {ranking_dict}")
        print(f"Comparing {cand1_id} (rank {ranking_dict.get(cand1_id)}) vs {cand2_id} (rank {ranking_dict.get(cand2_id)})")
        
        # Check for the specific ballot pattern (Begich 1st, Palin/Peltola tied 2nd)
        if ranking_dict.get('candidate-2') == 1 and ranking_dict.get('candidate-1') == 2 and ranking_dict.get('candidate-0') == 2:
            print("*** THIS IS THE BALLOT WITH BEGICH 1st, PALIN/PELTOLA tied 2nd ***")
    
    comparison = infer_pairwise_comparison_from_ballot_alaska_rules(
        ranking_dict, cand1_id, cand2_id
    )
    
    if (cand1_id == 'candidate-2' and cand2_id == 'candidate-1') or \
       (cand1_id == 'candidate-1' and cand2_id == 'candidate-2'):
        print(f"Alaska rules returned: {comparison}")
        if comparison:
            menu, winners = comparison
            if len(winners) == 2:
                print(f"Result: TIE (both in winners)")
            elif cand1_id in winners:
                print(f"Result: {cand1_id} WINS")
            elif cand2_id in winners:
                print(f"Result: {cand2_id} WINS")
        else:
            print(f"Result: UNDEFINED")
        print(f"=== END DEBUG ===\n")
    
    if comparison is None:
        return 'undefined'
    
    menu, winners = comparison
    
    if len(winners) == 2:
        return 'tie'
    elif cand1_id in winners:
        return 'cand1_wins'
    elif cand2_id in winners:
        return 'cand2_wins'
    else:
        return 'undefined'


def format_ballot_for_display(ballot: Any, poll_candidates: List[Dict]) -> Dict:
    """Format a ballot for display."""
    candidate_lookup = {c['id']: c['name'] for c in poll_candidates}
    if ballot.write_ins:
        for write_in in ballot.write_ins:
            candidate_lookup[write_in['id']] = write_in['name']
    
    display_rankings = []
    for ranking in ballot.rankings:
        display_rankings.append({
            'candidate_id': ranking['candidate_id'],
            'candidate_name': candidate_lookup.get(ranking['candidate_id'], ranking['candidate_id']),
            'rank': ranking['rank']
        })
    
    return {
        'ballot_id': str(ballot.id),
        'rankings': display_rankings,
        'count': ballot.count,
        'submitted_at': ballot.submitted_at.isoformat() if ballot.submitted_at else None
    }


@router.get("/poll/{poll_id}/pairwise")
async def get_pairwise_ballots(
    poll_id: str,
    cand1_id: str = Query(..., description="First candidate ID"),
    cand2_id: str = Query(..., description="Second candidate ID"),
    group: Optional[str] = Query(None, description="Load specific group: cand1_wins, cand2_wins, tie, undefined"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Max ballots to return"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get pairwise comparison data.
    - If no group specified: returns summary + initial ballots
    - If group specified: returns paginated ballots for that group
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
    
    # Get all ballots
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.is_test == False
    )
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    # Process all ballots to get complete statistics
    grouped_ballots = {
        'cand1_wins': [],
        'cand2_wins': [],
        'tie': [],
        'undefined': []
    }
    
    stats = {
        'cand1_wins': 0,
        'cand2_wins': 0,
        'tie': 0,
        'undefined': 0
    }
    
    for ballot in ballots:
        comparison_result = process_ballot_for_comparison(
            ballot.rankings,
            cand1_id,
            cand2_id,
            ballot.write_ins
        )
        
        stats[comparison_result] += ballot.count
        formatted_ballot = format_ballot_for_display(ballot, poll.candidates)
        grouped_ballots[comparison_result].append(formatted_ballot)
    
    # Sort ballots within each group by the ranks of the compared candidates
    def get_sort_key(ballot_display, cand1_id, cand2_id):
        """Sort key: first by cand1's rank, then by cand2's rank"""
        cand1_rank = 999  # Default for unranked
        cand2_rank = 999
        
        for ranking in ballot_display['rankings']:
            if ranking['candidate_id'] == cand1_id:
                cand1_rank = ranking['rank']
            elif ranking['candidate_id'] == cand2_id:
                cand2_rank = ranking['rank']
        
        return (cand1_rank, cand2_rank)
    
    # Sort cand1_wins and cand2_wins groups
    grouped_ballots['cand1_wins'].sort(key=lambda b: get_sort_key(b, cand1_id, cand2_id))
    grouped_ballots['cand2_wins'].sort(key=lambda b: get_sort_key(b, cand1_id, cand2_id))
    # Ties and undefined can remain unsorted or you can sort them too
    
    # Get candidate names
    candidate_lookup = {c['id']: c['name'] for c in poll.candidates}
    cand1_name = candidate_lookup.get(cand1_id)
    cand2_name = candidate_lookup.get(cand2_id)
    
    if not cand1_name or not cand2_name:
        for ballot in ballots[:10]:
            if ballot.write_ins:
                for write_in in ballot.write_ins:
                    if write_in['id'] == cand1_id:
                        cand1_name = write_in['name']
                    if write_in['id'] == cand2_id:
                        cand2_name = write_in['name']
                    if cand1_name and cand2_name:
                        break
    
    comparison_info = {
        'cand1': {'id': cand1_id, 'name': cand1_name or cand1_id},
        'cand2': {'id': cand2_id, 'name': cand2_name or cand2_id}
    }
    
    # If requesting specific group, return paginated data for that group
    if group and group in grouped_ballots:
        paginated_ballots = grouped_ballots[group][offset:offset + limit]
        return {
            'poll_id': str(poll.id),
            'poll_title': poll.title,
            'comparison': comparison_info,
            'group': group,
            'ballots': paginated_ballots,
            'total_in_group': len(grouped_ballots[group]),
            'stats': {group: stats[group]},
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < len(grouped_ballots[group])
        }
    
    # Otherwise return summary with initial batch of ballots
    initial_batch_size = 10  # Start with 10 ballots per group
    
    # Calculate ballots with valid comparisons (not undefined)
    ballots_with_comparison = len(ballots) - len(grouped_ballots['undefined'])
    votes_with_comparison = sum(stats.values()) - stats.get('undefined', 0)
    
    return {
        'poll_id': str(poll.id),
        'poll_title': poll.title,
        'comparison': comparison_info,
        'ballots': {
            'cand1_wins': grouped_ballots['cand1_wins'][:initial_batch_size],
            'cand2_wins': grouped_ballots['cand2_wins'][:initial_batch_size],
            'tie': grouped_ballots['tie'][:initial_batch_size],
            'undefined': grouped_ballots['undefined'][:initial_batch_size]
        },
        'stats': stats,
        'total_ballots': len(ballots),
        'total_votes': sum(stats.values()),
        'ballots_with_comparison': ballots_with_comparison,
        'votes_with_comparison': votes_with_comparison,
        'ballot_counts': {
            'cand1_wins': len(grouped_ballots['cand1_wins']),
            'cand2_wins': len(grouped_ballots['cand2_wins']),
            'tie': len(grouped_ballots['tie']),
            'undefined': len(grouped_ballots['undefined'])
        }
    }


@router.get("/poll/{poll_id}/all-comparisons")
async def get_all_comparisons(
    poll_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all available pairwise comparisons with quick stats."""
    
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
    
    # Get all candidates including write-ins
    all_candidates = list(poll.candidates)
    
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.is_test == False
    )
    result = await db.execute(stmt)
    ballots = result.scalars().all()
    
    # Collect unique write-ins
    write_in_candidates = {}
    for ballot in ballots:
        if ballot.write_ins:
            for write_in in ballot.write_ins:
                if write_in['id'] not in write_in_candidates:
                    write_in_candidates[write_in['id']] = {
                        'id': write_in['id'],
                        'name': write_in['name'],
                        'is_write_in': True
                    }
    
    all_candidates.extend(write_in_candidates.values())
    
    # Generate all pairwise combinations with quick stats
    comparisons = []
    for i, cand1 in enumerate(all_candidates):
        for cand2 in all_candidates[i+1:]:
            quick_stats = {
                'cand1_wins': 0,
                'cand2_wins': 0,
                'tie': 0,
                'undefined': 0
            }
            
            for ballot in ballots:
                result = process_ballot_for_comparison(
                    ballot.rankings,
                    cand1['id'],
                    cand2['id'],
                    ballot.write_ins
                )
                quick_stats[result] += ballot.count
            
            comparisons.append({
                'cand1': {
                    'id': cand1['id'],
                    'name': cand1['name'],
                    'is_write_in': cand1.get('is_write_in', False)
                },
                'cand2': {
                    'id': cand2['id'],
                    'name': cand2['name'],
                    'is_write_in': cand2.get('is_write_in', False)
                },
                'quick_stats': quick_stats
            })
    
    return {
        'poll_id': str(poll.id),
        'poll_title': poll.title,
        'comparisons': comparisons,
        'total_candidates': len(all_candidates),
        'total_comparisons': len(comparisons)
    }
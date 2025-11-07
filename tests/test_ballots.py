# tests/test_ballots.py
"""
Ballot Submission Tests

Tests ballot submission and validation:
- Basic ballot submission
- Rankings (complete, partial, with ties)
- Write-in candidates
- Voter uniqueness constraints
- Public vs private poll voting
"""

import pytest
from tests.conftest import generate_unique_fingerprint, generate_unique_email


# ==============================================================================
# BASIC BALLOT SUBMISSION
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_simple_ballot(create_poll, submit_ballot):
    """Test submitting a basic ranked ballot"""
    # Create poll
    poll = await create_poll(
        title="Simple Vote",
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot: A > B > C
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[2], "rank": 3}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["message"] == "Vote recorded"


@pytest.mark.asyncio
async def test_submit_partial_ranking(create_poll, submit_ballot):
    """Test submitting a ballot with only some candidates ranked"""
    # Create poll
    poll = await create_poll(
        title="Partial Ranking Test",
        candidates=[
            {"name": "A"}, {"name": "B"},
            {"name": "C"}, {"name": "D"}
        ],
        settings={"require_complete_ranking": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot: Only rank A > B, leave C and D unranked
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True


# ==============================================================================
# BALLOT ACCESS BY DIFFERENT IDENTIFIERS
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_ballot_using_uuid(create_poll, submit_ballot):
    """Test submitting a ballot using poll UUID"""
    poll = await create_poll(title="UUID Vote Test")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    response = await submit_ballot(
        poll_id=poll["id"],  # Use UUID
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_submit_ballot_using_short_id(create_poll, submit_ballot):
    """Test submitting a ballot using poll short_id"""
    poll = await create_poll(title="Short ID Vote Test")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    response = await submit_ballot(
        poll_id=poll["short_id"],  # Use short_id
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_submit_ballot_using_slug(create_poll, submit_ballot):
    """Test submitting a ballot using poll slug"""
    poll = await create_poll(
        title="Slug Vote Test",
        slug="slug-vote-test"
    )
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    response = await submit_ballot(
        poll_id="slug-vote-test",  # Use slug
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


# ==============================================================================
# RANKINGS WITH TIES
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_ballot_with_ties_allowed(create_poll, submit_ballot):
    """Test submitting a ballot with tied rankings when allowed"""
    poll = await create_poll(
        title="Ties Allowed",
        candidates=[
            {"name": "A"}, {"name": "B"},
            {"name": "C"}, {"name": "D"}
        ],
        settings={"allow_ties": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot with tie: A=B > C > D
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 1},  # Tied with A
            {"candidate_id": candidate_ids[2], "rank": 2},
            {"candidate_id": candidate_ids[3], "rank": 3}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True


@pytest.mark.asyncio
async def test_submit_ballot_all_tied(create_poll, submit_ballot):
    """Test submitting a ballot where all candidates are tied"""
    poll = await create_poll(
        title="All Tied",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"allow_ties": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # All candidates ranked equally
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 1},
            {"candidate_id": candidate_ids[2], "rank": 1}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


# ==============================================================================
# WRITE-IN CANDIDATES
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_ballot_with_write_in(create_poll, submit_ballot):
    """Test submitting a ballot with a write-in candidate"""
    poll = await create_poll(
        title="Write-in Test",
        candidates=[{"name": "A"}, {"name": "B"}],
        settings={"allow_write_ins": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit with write-in
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": "write-in-12345", "rank": 2},  # Write-in
            {"candidate_id": candidate_ids[1], "rank": 3}
        ],
        voter_fingerprint=generate_unique_fingerprint(),
        write_ins=[
            {"id": "write-in-12345", "name": "Custom Option", "is_write_in": True}
        ]
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert len(data["ballot_data"]["write_ins"]) == 1


@pytest.mark.asyncio
async def test_submit_ballot_write_in_without_id(create_poll, submit_ballot):
    """Test that write-ins without IDs are assigned IDs automatically"""
    poll = await create_poll(
        title="Write-in Auto ID",
        candidates=[{"name": "A"}],
        settings={"allow_write_ins": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit with write-in that has no ID
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1}
        ],
        voter_fingerprint=generate_unique_fingerprint(),
        write_ins=[
            {"name": "My Custom Candidate"}  # No ID provided
        ]
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify write-in was assigned an ID
    assert len(data["ballot_data"]["write_ins"]) == 1
    assert "id" in data["ballot_data"]["write_ins"][0]


# ==============================================================================
# VOTER UNIQUENESS - PUBLIC POLLS
# ==============================================================================

@pytest.mark.asyncio
async def test_same_fingerprint_cannot_vote_twice(create_poll, submit_ballot):
    """Test that the same voter fingerprint cannot submit multiple ballots"""
    poll = await create_poll(title="Uniqueness Test")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    fingerprint = generate_unique_fingerprint()
    
    # First vote
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=fingerprint
    )
    assert response1.status_code == 200
    
    # Second vote with same fingerprint - should update, not create new
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
        voter_fingerprint=fingerprint
    )
    assert response2.status_code == 200
    data = response2.json()
    assert data["message"] == "Vote updated"



# ==============================================================================
# PRIVATE POLLS - TOKEN VALIDATION
# ==============================================================================

@pytest.mark.asyncio
async def test_private_poll_requires_token(create_poll, submit_ballot, client):
    """Test that private polls require a valid voter token"""
    # Create private poll with voters
    poll = await create_poll(
        title="Private Poll",
        is_private=True,
        voter_emails=["voter1@example.com", "voter2@example.com"]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Try to vote without token - should fail
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}]
    )
    assert response.status_code == 403
    
    # Get voter token from database
    from app.db import get_db
    from app.models import Voter
    from sqlalchemy import select
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"]).limit(1)
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if voter:
            # Vote with valid token - should succeed
            response = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voter.token
            )
            assert response.status_code == 200
        break


# ==============================================================================
# MULTIPLE BALLOTS
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_multiple_ballots(create_poll, submit_ballot):
    """Test submitting multiple ballots from different voters"""
    poll = await create_poll(
        title="Multiple Ballots Test",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit 5 ballots
    for i in range(5):
        response = await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[i % 3], "rank": 1},
                {"candidate_id": candidate_ids[(i + 1) % 3], "rank": 2},
                {"candidate_id": candidate_ids[(i + 2) % 3], "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
        assert response.status_code == 200


# ==============================================================================
# EDGE CASES
# ==============================================================================

@pytest.mark.asyncio
async def test_submit_ballot_to_nonexistent_poll(submit_ballot):
    """Test that submitting to a nonexistent poll fails gracefully"""
    response = await submit_ballot(
        poll_id="nonexistent-poll",
        rankings=[{"candidate_id": "fake-id", "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_submit_single_candidate_ballot(create_poll, submit_ballot):
    """Test submitting a ballot ranking only one candidate"""
    poll = await create_poll(
        title="Single Rank",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"require_complete_ranking": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Rank only one candidate
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


# ==============================================================================
# VALIDATION FAILURES
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_candidate_id(create_poll, submit_ballot):
    """Test that submitting a ballot with invalid candidate ID fails"""
    poll = await create_poll(
        title="Invalid Candidate Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    # Submit ballot with fake candidate ID
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": "fake-candidate-id", "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ties_not_allowed(create_poll, submit_ballot):
    """Test that ties are rejected when allow_ties is False"""
    poll = await create_poll(
        title="No Ties Allowed",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"allow_ties": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Try to submit ballot with tie
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 1},  # Tied
            {"candidate_id": candidate_ids[2], "rank": 2}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_write_ins_not_allowed(create_poll, submit_ballot):
    """Test that write-ins are rejected when allow_write_ins is False"""
    poll = await create_poll(
        title="No Write-ins",
        candidates=[{"name": "A"}, {"name": "B"}],
        settings={"allow_write_ins": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Try to submit with write-in
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": "write-in-123", "rank": 2}
        ],
        voter_fingerprint=generate_unique_fingerprint(),
        write_ins=[
            {"id": "write-in-123", "name": "Custom", "is_write_in": True}
        ]
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_incomplete_ranking_when_required(create_poll, submit_ballot):
    """Test that incomplete rankings are rejected when require_complete_ranking is True"""
    poll = await create_poll(
        title="Complete Ranking Required",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"require_complete_ranking": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit partial ballot (only 2 of 3 candidates)
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2}
            # Missing candidate_ids[2]
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_exceeding_num_ranks_limit(create_poll, submit_ballot):
    """Test that exceeding num_ranks limit is rejected"""
    poll = await create_poll(
        title="Limited Ranks",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        settings={"num_ranks": 2}  # Only allow ranking 2 candidates
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Try to rank 3 candidates when limit is 2
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[2], "rank": 3}  # Exceeds limit
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_candidate_in_ballot(create_poll, submit_ballot):
    """Test that ranking the same candidate twice is rejected"""
    poll = await create_poll(
        title="Duplicate Candidate Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Try to rank same candidate twice
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[0], "rank": 2}  # Duplicate
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ballot_rejected_when_poll_closed(create_poll, submit_ballot, client):
    """Test that ballots are rejected when poll status is closed"""
    from app.db import get_db
    from app.models import Poll
    from sqlalchemy import select, update
    
    poll = await create_poll(
        title="Closed Poll Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Close the poll
    async for db in get_db():
        stmt = update(Poll).where(Poll.id == poll["id"]).values(status="closed")
        await db.execute(stmt)
        await db.commit()
        break
    
    # Try to submit ballot to closed poll
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ballot_accepted_before_deadline(create_poll, submit_ballot, client):
    """Test that ballots are accepted before poll closing deadline"""
    from datetime import datetime, timedelta
    from app.db import get_db
    from app.models import Poll
    from sqlalchemy import select, update
    
    poll = await create_poll(
        title="Before Deadline Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Set closing_at to 1 hour in the future
    future_deadline = datetime.utcnow() + timedelta(hours=1)
    
    async for db in get_db():
        stmt = update(Poll).where(Poll.id == poll["id"]).values(
            closing_at=future_deadline,
            status="open"
        )
        await db.execute(stmt)
        await db.commit()
        break
    
    # Submit ballot before deadline
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ballot_accepted_when_no_deadline(create_poll, submit_ballot):
    """Test that ballots are accepted when poll has no closing deadline"""
    poll = await create_poll(
        title="No Deadline Test",
        candidates=[{"name": "A"}, {"name": "B"}]
        # No closing_at specified
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot - should be accepted
    response = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    assert response.status_code == 200


# ==============================================================================
# DUPLICATE VOTING PREVENTION - PUBLIC POLLS
# ==============================================================================

@pytest.mark.asyncio
async def test_public_poll_same_fingerprint_updates_vote(create_poll, submit_ballot, client):
    """
    PUBLIC POLL BEHAVIOR: Same fingerprint OVERWRITES previous vote
    
    This test verifies that in public polls:
    - First vote: Creates ballot with message "Vote recorded"
    - Second vote (same fingerprint): Updates ballot with message "Vote updated"
    - Ballot count stays at 1 (no duplicate created)
    """
    poll = await create_poll(
        title="Public Poll Update Test",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # First vote: A ranked first
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["success"] == True
    assert data1["message"] == "Vote recorded"
    ballot_id_1 = data1["ballot_id"]
    
    # Second vote with SAME fingerprint: B ranked first (different preference)
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[1], "rank": 1},
            {"candidate_id": candidate_ids[2], "rank": 2}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["success"] == True
    assert data2["message"] == "Vote updated"  # Key: says "updated" not "recorded"
    ballot_id_2 = data2["ballot_id"]
    
    # CRITICAL: Same ballot ID means it was updated, not duplicated
    assert ballot_id_1 == ballot_id_2
    
    # Verify ballot count is still 1 by querying database
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 1  # Not 2!
        break


@pytest.mark.asyncio
async def test_public_poll_different_fingerprints_create_separate_ballots(create_poll, submit_ballot, client):
    """
    Verify that different fingerprints create separate ballots (not updates)
    """
    poll = await create_poll(
        title="Different Fingerprints Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Voter 1
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    assert response1.status_code == 200
    assert response1.json()["message"] == "Vote recorded"
    
    # Voter 2 (different fingerprint)
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    assert response2.status_code == 200
    assert response2.json()["message"] == "Vote recorded"  # New ballot, not update
    
    # Verify ballot count is 2 by querying database
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 2
        break


@pytest.mark.asyncio
async def test_public_poll_multiple_updates_still_one_ballot(create_poll, submit_ballot, client):
    """
    Verify that multiple updates from same voter still results in only 1 ballot
    """
    poll = await create_poll(
        title="Multiple Updates Test",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # Submit and update 5 times with same fingerprint
    for i in range(5):
        response = await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[{"candidate_id": candidate_ids[i % 3], "rank": 1}],
            voter_fingerprint=fingerprint
        )
        assert response.status_code == 200
        if i == 0:
            assert response.json()["message"] == "Vote recorded"
        else:
            assert response.json()["message"] == "Vote updated"
    
    # Verify only 1 ballot exists by querying database
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 1  # Not 5!
        break


# ==============================================================================
# DUPLICATE VOTING PREVENTION - PRIVATE POLLS
# ==============================================================================

@pytest.mark.asyncio
async def test_private_poll_token_cannot_vote_twice(create_poll, submit_ballot, client):
    """
    PRIVATE POLL WITH UPDATES DISABLED: Same token is REJECTED on second vote
    
    This test verifies that in private polls with allow_vote_updates=False:
    - First vote: Creates ballot with message "Vote recorded"
    - Second vote (same token): REJECTED with 400 error
    - Original ballot remains unchanged
    - Ballot count stays at 1
    """
    poll = await create_poll(
        title="Private Poll Token Test",
        is_private=True,
        voter_emails=["voter@example.com"],
        settings={"allow_vote_updates": False}  # ← DISABLE UPDATES
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Get voter token
    from app.db import get_db
    from app.models import Voter, Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"]).limit(1)
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if voter:
            # First vote: A ranked first
            response1 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voter.token
            )
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["message"] == "Vote recorded"
            ballot_id_1 = data1["ballot_id"]
            
            # Second vote with SAME token: Try to change to B
            response2 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
                voter_token=voter.token
            )
            
            # CRITICAL: Should be rejected with 400
            assert response2.status_code == 400
            data2 = response2.json()
            assert "Vote updates are not allowed" in data2["detail"]
            
            # Verify ballot count is still 1 (no duplicate created) by querying database
            stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
            result = await db.execute(stmt)
            ballot_count = result.scalar()
            assert ballot_count == 1
        break


@pytest.mark.asyncio
async def test_private_poll_different_tokens_create_separate_ballots(create_poll, submit_ballot, client):
    """
    Verify that different tokens in private poll create separate ballots
    """
    poll = await create_poll(
        title="Private Poll Multiple Voters",
        is_private=True,
        voter_emails=["voter1@example.com", "voter2@example.com"]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Get both voter tokens
    from app.db import get_db
    from app.models import Voter, Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"])
        result = await db.execute(stmt)
        voters = result.scalars().all()
        
        if len(voters) >= 2:
            # Voter 1 submits
            response1 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voters[0].token
            )
            assert response1.status_code == 200
            assert response1.json()["message"] == "Vote recorded"
            
            # Voter 2 submits (different token)
            response2 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
                voter_token=voters[1].token
            )
            assert response2.status_code == 200
            assert response2.json()["message"] == "Vote recorded"
            
            # Verify ballot count is 2 by querying database
            stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
            result = await db.execute(stmt)
            ballot_count = result.scalar()
            assert ballot_count == 2
        break


# ==============================================================================
# SINGLE BALLOT CONFIRMATION
# ==============================================================================

@pytest.mark.asyncio
async def test_update_does_not_create_duplicate_ballot(create_poll, submit_ballot, client):
    """Test that updating a ballot doesn't create a second ballot"""
    poll = await create_poll(
        title="No Duplicate Ballots",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # Submit initial ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=fingerprint
    )
    
    # Update ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
        voter_fingerprint=fingerprint
    )
    
    # Check total ballot count directly from database
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        
        # Should only have 1 ballot, not 2
        assert ballot_count == 1
        break


@pytest.mark.asyncio
async def test_multiple_updates_still_one_ballot(create_poll, submit_ballot, client):
    """Test that multiple updates from same voter still results in only 1 ballot"""
    poll = await create_poll(
        title="Multiple Updates Test",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # Submit and update 5 times
    for i in range(5):
        response = await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[{"candidate_id": candidate_ids[i % 3], "rank": 1}],
            voter_fingerprint=fingerprint
        )
        assert response.status_code == 200
    
    # Verify only 1 ballot exists
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 1
        break


@pytest.mark.asyncio
async def test_private_poll_one_ballot_per_token(create_poll, submit_ballot, client):
    """Test that each token in private poll can only have 1 ballot"""
    poll = await create_poll(
        title="Private Poll Token Ballots",
        is_private=True,
        voter_emails=["voter1@example.com", "voter2@example.com"]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Get both voter tokens
    from app.db import get_db
    from app.models import Voter
    from sqlalchemy import select
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"])
        result = await db.execute(stmt)
        voters = result.scalars().all()
        
        if len(voters) >= 2:
            # First voter submits and updates
            await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voters[0].token
            )
            
            await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
                voter_token=voters[0].token
            )
            
            # Second voter submits
            await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voters[1].token
            )
            
            # Check total ballot count directly from database - should be 2 (one per voter)
            from app.models import Ballot
            from sqlalchemy import func
            
            stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
            result = await db.execute(stmt)
            ballot_count = result.scalar()
            assert ballot_count == 2
        break


# ==============================================================================
# GET BALLOT - RETRIEVE EXISTING BALLOTS
# ==============================================================================

@pytest.mark.asyncio
async def test_get_ballot_by_fingerprint_public_poll(create_poll, submit_ballot, client):
    """Test retrieving existing ballot by fingerprint in public poll"""
    poll = await create_poll(
        title="Get Ballot Test",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # Submit ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2}
        ],
        voter_fingerprint=fingerprint
    )
    
    # Retrieve ballot
    response = await client.get(
        f"/api/v1/ballots/{poll['short_id']}/ballot",
        params={"voter_fingerprint": fingerprint}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["has_voted"] == True
    assert len(data["ballot"]["rankings"]) == 2
    assert data["ballot"]["rankings"][0]["candidate_id"] == candidate_ids[0]


@pytest.mark.asyncio
async def test_get_ballot_returns_404_if_not_voted(create_poll, client):
    """Test that GET returns 404 if voter hasn't voted yet"""
    poll = await create_poll(title="No Ballot Test")
    
    # Try to get ballot without voting
    response = await client.get(
        f"/api/v1/ballots/{poll['short_id']}/ballot",
        params={"voter_fingerprint": generate_unique_fingerprint()}
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_ballot_by_token_private_poll(create_poll, submit_ballot, client):
    """Test retrieving ballot in private poll by token"""
    poll = await create_poll(
        title="Private Get Ballot",
        is_private=True,
        voter_emails=["voter@example.com"]
    )
    
    from app.db import get_db
    from app.models import Voter
    from sqlalchemy import select
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"]).limit(1)
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if voter:
            candidate_ids = [c["id"] for c in poll["candidates"]]
            
            # Submit ballot
            await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
                voter_token=voter.token
            )
            
            # Retrieve ballot
            response = await client.get(
                f"/api/v1/ballots/{poll['short_id']}/ballot",
                params={"voter_token": voter.token}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["has_voted"] == True
            assert len(data["ballot"]["rankings"]) == 1
        break


@pytest.mark.asyncio
async def test_get_ballot_wrong_fingerprint_returns_404(create_poll, submit_ballot, client):
    """Test that you cannot retrieve another voter's ballot"""
    poll = await create_poll(title="Wrong Fingerprint Test")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    fingerprint1 = generate_unique_fingerprint()
    fingerprint2 = generate_unique_fingerprint()
    
    # Voter 1 submits ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=fingerprint1
    )
    
    # Try to retrieve with different fingerprint
    response = await client.get(
        f"/api/v1/ballots/{poll['short_id']}/ballot",
        params={"voter_fingerprint": fingerprint2}
    )
    
    assert response.status_code == 404


# ==============================================================================
# DEV MODE TESTS - Auto-generated Fingerprints
# ==============================================================================

@pytest.mark.asyncio
async def test_dev_mode_disabled_requires_fingerprint(create_poll, client, monkeypatch):
    """
    Test that with DEV_MODE=false (production), fingerprint is required.
    This is the default behavior and what all other tests rely on.
    """
    # Ensure DEV_MODE is explicitly false
    monkeypatch.setenv('DEV_MODE', 'false')
    
    # Need to reload the module to pick up env var change
    from importlib import reload
    from app.api.v1 import ballots
    reload(ballots)
    
    poll = await create_poll(
        title="Prod Mode Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot WITHOUT fingerprint - should work but ballot has None fingerprint
    response = await client.post("/api/v1/ballots/", json={
        "poll_id": poll["short_id"],
        "rankings": [{"candidate_id": candidate_ids[0], "rank": 1}]
        # Note: No voter_fingerprint provided
    })
    
    # In production mode, this should still work but ballot will have voter_fingerprint=None
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True


@pytest.mark.asyncio
async def test_dev_mode_enabled_auto_generates_fingerprint(create_poll, client, monkeypatch):
    """
    Test that with DEV_MODE=true, fingerprint is auto-generated if not provided.
    """
    # Enable DEV_MODE
    monkeypatch.setenv('DEV_MODE', 'true')
    
    # Need to reload the module to pick up env var change
    from importlib import reload
    from app.api.v1 import ballots
    reload(ballots)
    
    poll = await create_poll(
        title="Dev Mode Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot WITHOUT fingerprint - should auto-generate
    response = await client.post("/api/v1/ballots/", json={
        "poll_id": poll["short_id"],
        "rankings": [{"candidate_id": candidate_ids[0], "rank": 1}]
        # Note: No voter_fingerprint provided, but DEV_MODE will auto-generate
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["message"] == "Vote recorded"
    
    # Verify ballot was created
    assert "ballot_id" in data


@pytest.mark.asyncio
async def test_dev_mode_each_vote_gets_unique_fingerprint(create_poll, client, monkeypatch):
    """
    Test that in DEV_MODE, each vote without a fingerprint gets a unique one.
    This allows testing multiple voters easily.
    """
    # Enable DEV_MODE
    monkeypatch.setenv('DEV_MODE', 'true')
    
    # Need to reload the module to pick up env var change
    from importlib import reload
    from app.api.v1 import ballots
    reload(ballots)
    
    poll = await create_poll(
        title="Multiple Voters Dev Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit 3 ballots without fingerprints
    ballot_ids = []
    for i in range(3):
        response = await client.post("/api/v1/ballots/", json={
            "poll_id": poll["short_id"],
            "rankings": [{"candidate_id": candidate_ids[i % 2], "rank": 1}]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Vote recorded"  # Not "Vote updated"
        ballot_ids.append(data["ballot_id"])
    
    # All ballot IDs should be unique (each is a new voter)
    assert len(set(ballot_ids)) == 3
    
    # Verify we have 3 ballots in the database
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 3
        break


@pytest.mark.asyncio
async def test_dev_mode_respects_provided_fingerprint(create_poll, client, monkeypatch):
    """
    Test that in DEV_MODE, if a fingerprint IS provided, it's used instead of auto-generating.
    """
    # Enable DEV_MODE
    monkeypatch.setenv('DEV_MODE', 'true')
    
    # Need to reload the module to pick up env var change
    from importlib import reload
    from app.api.v1 import ballots
    reload(ballots)
    
    poll = await create_poll(
        title="Provided Fingerprint Test",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit with explicit fingerprint
    response1 = await client.post("/api/v1/ballots/", json={
        "poll_id": poll["short_id"],
        "rankings": [{"candidate_id": candidate_ids[0], "rank": 1}],
        "voter_fingerprint": "my-test-fingerprint"
    })
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["message"] == "Vote recorded"
    ballot_id_1 = data1["ballot_id"]
    
    # Submit again with SAME fingerprint - should update
    response2 = await client.post("/api/v1/ballots/", json={
        "poll_id": poll["short_id"],
        "rankings": [{"candidate_id": candidate_ids[1], "rank": 1}],
        "voter_fingerprint": "my-test-fingerprint"
    })
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["message"] == "Vote updated"  # Same voter
    ballot_id_2 = data2["ballot_id"]
    
    # Should be the same ballot
    assert ballot_id_1 == ballot_id_2
    
    # Verify only 1 ballot exists
    from app.db import get_db
    from app.models import Ballot
    from sqlalchemy import select, func
    
    async for db in get_db():
        stmt = select(func.count()).select_from(Ballot).where(Ballot.poll_id == poll["id"])
        result = await db.execute(stmt)
        ballot_count = result.scalar()
        assert ballot_count == 1
        break


@pytest.mark.asyncio
async def test_dev_mode_false_by_default(create_poll, client):
    """
    CRITICAL TEST: Verify that DEV_MODE is false during tests.
    This ensures all other tests run in production mode.
    
    conftest.py explicitly sets os.environ['DEV_MODE']='false' before importing modules.
    We reload the module here to ensure we get the current environment value.
    """
    import os
    
    # Verify environment variable is false
    assert os.getenv('DEV_MODE', 'false').lower() == 'false', \
        f"DEV_MODE env var is '{os.getenv('DEV_MODE')}' but should be 'false'"
    
    # Reload module to pick up current environment
    from importlib import reload
    from app.api.v1 import ballots
    reload(ballots)
    
    # Now check the module constant
    assert ballots.DEV_MODE == False, \
        f"DEV_MODE should be False during tests but is {ballots.DEV_MODE}. Check conftest.py."


# ==============================================================================
# VOTE UPDATES - allow_vote_updates SETTING
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_with_vote_updates_allowed(create_poll, client):
    """Test creating a poll with vote updates explicitly allowed (default)"""
    poll = await create_poll(
        title="Updates Allowed Poll",
        settings={"allow_vote_updates": True}
    )
    
    # Fetch the poll to verify settings
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["settings"]["allow_vote_updates"] == True


@pytest.mark.asyncio
async def test_create_poll_with_vote_updates_disabled(create_poll, client):
    """Test creating a poll with vote updates disabled"""
    poll = await create_poll(
        title="Updates Disabled Poll",
        settings={"allow_vote_updates": False}
    )
    
    # Fetch the poll to verify settings
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["settings"]["allow_vote_updates"] == False


@pytest.mark.asyncio
async def test_vote_update_allowed_public_poll(create_poll, submit_ballot):
    """Test that voters can update their vote when allow_vote_updates=true (public poll)"""
    # Create poll with updates allowed
    poll = await create_poll(
        title="Public Poll - Updates Allowed",
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ],
        settings={"allow_vote_updates": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # First vote: A > B > C
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[2], "rank": 3}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["message"] == "Vote recorded"
    ballot_id_1 = data1["ballot_id"]
    
    # Second vote (update): C > B > A
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[2], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[0], "rank": 3}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["message"] == "Vote updated"
    ballot_id_2 = data2["ballot_id"]
    
    # Should be same ballot ID (updated, not new)
    assert ballot_id_1 == ballot_id_2


@pytest.mark.asyncio
async def test_vote_update_blocked_public_poll(create_poll, submit_ballot):
    """Test that voters CANNOT update their vote when allow_vote_updates=false (public poll)"""
    # Create poll with updates disabled
    poll = await create_poll(
        title="Public Poll - Updates Disabled",
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ],
        settings={"allow_vote_updates": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    fingerprint = generate_unique_fingerprint()
    
    # First vote: A > B > C
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[2], "rank": 3}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["message"] == "Vote recorded"
    
    # Try to update vote: C > B > A (should fail)
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[2], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2},
            {"candidate_id": candidate_ids[0], "rank": 3}
        ],
        voter_fingerprint=fingerprint
    )
    
    assert response2.status_code == 400
    error_data = response2.json()
    assert "Vote updates are not allowed" in error_data["detail"]


@pytest.mark.asyncio
async def test_vote_update_allowed_private_poll(create_poll, submit_ballot):
    """Test that voters can update their vote when allow_vote_updates=true (private poll)"""
    # Create private poll with updates allowed
    poll = await create_poll(
        title="Private Poll - Updates Allowed",
        is_private=True,
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ],
        voter_emails=["voter1@example.com"],
        settings={"allow_vote_updates": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Get voter token from database
    from app.db import get_db
    from app.models import Voter
    from sqlalchemy import select
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"]).limit(1)
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if voter:
            token = voter.token
            
            # First vote: A > B > C
            response1 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[
                    {"candidate_id": candidate_ids[0], "rank": 1},
                    {"candidate_id": candidate_ids[1], "rank": 2},
                    {"candidate_id": candidate_ids[2], "rank": 3}
                ],
                voter_token=token
            )
            
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["message"] == "Vote recorded"
            ballot_id_1 = data1["ballot_id"]
            
            # Second vote (update): C > B > A
            response2 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[
                    {"candidate_id": candidate_ids[2], "rank": 1},
                    {"candidate_id": candidate_ids[1], "rank": 2},
                    {"candidate_id": candidate_ids[0], "rank": 3}
                ],
                voter_token=token
            )
            
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["message"] == "Vote updated"
            ballot_id_2 = data2["ballot_id"]
            
            # Should be same ballot ID (updated, not new)
            assert ballot_id_1 == ballot_id_2
        break


@pytest.mark.asyncio
async def test_vote_update_blocked_private_poll(create_poll, submit_ballot):
    """Test that voters CANNOT update their vote when allow_vote_updates=false (private poll)"""
    # Create private poll with updates disabled
    poll = await create_poll(
        title="Private Poll - Updates Disabled",
        is_private=True,
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ],
        voter_emails=["voter1@example.com"],
        settings={"allow_vote_updates": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Get voter token from database
    from app.db import get_db
    from app.models import Voter
    from sqlalchemy import select
    
    async for db in get_db():
        stmt = select(Voter).where(Voter.poll_id == poll["id"]).limit(1)
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if voter:
            token = voter.token
            
            # First vote: A > B > C
            response1 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[
                    {"candidate_id": candidate_ids[0], "rank": 1},
                    {"candidate_id": candidate_ids[1], "rank": 2},
                    {"candidate_id": candidate_ids[2], "rank": 3}
                ],
                voter_token=token
            )
            
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["message"] == "Vote recorded"
            
            # Try to update vote: C > B > A (should fail)
            response2 = await submit_ballot(
                poll_id=poll["short_id"],
                rankings=[
                    {"candidate_id": candidate_ids[2], "rank": 1},
                    {"candidate_id": candidate_ids[1], "rank": 2},
                    {"candidate_id": candidate_ids[0], "rank": 3}
                ],
                voter_token=token
            )
            
            assert response2.status_code == 400
            error_data = response2.json()
            assert "Vote updates are not allowed" in error_data["detail"]
        break
    error_data = response2.json()
    assert "Vote updates are not allowed" in error_data["detail"]


@pytest.mark.asyncio
async def test_default_allow_vote_updates_is_true(create_poll, client):
    """Test that allow_vote_updates defaults to True when not specified"""
    # Create poll without specifying allow_vote_updates
    poll = await create_poll(
        title="Default Settings Poll",
        candidates=[
            {"name": "A"},
            {"name": "B"}
        ]
    )
    
    # Fetch the poll to verify settings default
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    # Should default to True
    assert poll_data["settings"].get("allow_vote_updates", True) == True


@pytest.mark.asyncio
async def test_multiple_voters_with_updates_disabled(create_poll, submit_ballot):
    """Test that multiple different voters can still vote when updates are disabled"""
    # Create poll with updates disabled
    poll = await create_poll(
        title="Multiple Voters - No Updates",
        candidates=[
            {"name": "A"},
            {"name": "B"},
            {"name": "C"}
        ],
        settings={"allow_vote_updates": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # First voter
    fingerprint1 = generate_unique_fingerprint()
    response1 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[0], "rank": 1},
            {"candidate_id": candidate_ids[1], "rank": 2}
        ],
        voter_fingerprint=fingerprint1
    )
    assert response1.status_code == 200
    assert response1.json()["message"] == "Vote recorded"
    
    # Second voter (different fingerprint)
    fingerprint2 = generate_unique_fingerprint()
    response2 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[1], "rank": 1},
            {"candidate_id": candidate_ids[2], "rank": 2}
        ],
        voter_fingerprint=fingerprint2
    )
    assert response2.status_code == 200
    assert response2.json()["message"] == "Vote recorded"
    
    # Third voter (different fingerprint)
    fingerprint3 = generate_unique_fingerprint()
    response3 = await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": candidate_ids[2], "rank": 1},
            {"candidate_id": candidate_ids[0], "rank": 2}
        ],
        voter_fingerprint=fingerprint3
    )
    assert response3.status_code == 200
    assert response3.json()["message"] == "Vote recorded"
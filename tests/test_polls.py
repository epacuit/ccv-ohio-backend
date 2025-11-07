# tests/test_polls.py
"""
Poll Creation Tests

Tests poll creation with various settings and configurations:
- Basic poll creation
- Different poll settings (allow_ties, write-ins, etc.)
- Access by UUID, short_id, and slug
- Private vs public polls
"""

import pytest
from httpx import AsyncClient


# ==============================================================================
# BASIC POLL CREATION
# ==============================================================================

@pytest.mark.asyncio
async def test_create_basic_poll(create_poll):
    """Test creating a simple poll with default settings"""
    poll = await create_poll(
        title="What should we have for lunch?",
        candidates=[
            {"name": "Pizza"},
            {"name": "Burgers"},
            {"name": "Salad"}
        ]
    )
    
    assert poll["short_id"]  # Should have a short ID
    assert len(poll["short_id"]) == 6  # Default short ID length
    assert poll["admin_token"]  # Should have admin token
    assert len(poll["candidates"]) == 3
    
    # Verify candidates have IDs assigned
    for candidate in poll["candidates"]:
        assert "id" in candidate
        assert candidate["id"].startswith("candidate-")


@pytest.mark.asyncio
async def test_create_poll_with_slug(create_poll, client):
    """Test creating a poll with a custom slug"""
    poll = await create_poll(
        title="Best Programming Language",
        slug="best-lang-2025",
        candidates=[
            {"name": "Python"},
            {"name": "JavaScript"},
            {"name": "Rust"}
        ]
    )
    
    assert poll["slug"] == "best-lang-2025"
    
    # Verify we can access the poll by slug
    response = await client.get(f"/api/v1/polls/best-lang-2025")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["slug"] == "best-lang-2025"


@pytest.mark.asyncio
async def test_create_poll_with_many_candidates(create_poll):
    """Test creating a poll with 10 candidates"""
    candidates = [{"name": f"Candidate {i}"} for i in range(1, 11)]
    
    poll = await create_poll(
        title="Top 10 Movies",
        candidates=candidates
    )
    
    assert len(poll["candidates"]) == 10


# ==============================================================================
# POLL ACCESS METHODS
# ==============================================================================

@pytest.mark.asyncio
async def test_access_poll_by_uuid(create_poll, client):
    """Test accessing a poll by its UUID"""
    poll = await create_poll(title="UUID Test Poll")
    
    response = await client.get(f"/api/v1/polls/{poll['id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["id"] == poll["id"]


@pytest.mark.asyncio
async def test_access_poll_by_short_id(create_poll, client):
    """Test accessing a poll by its short_id"""
    poll = await create_poll(title="Short ID Test Poll")
    
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["short_id"] == poll["short_id"]


@pytest.mark.asyncio
async def test_access_poll_by_slug(create_poll, client):
    """Test accessing a poll by its custom slug"""
    poll = await create_poll(
        title="Slug Test Poll",
        slug="my-test-slug"
    )
    
    response = await client.get("/api/v1/polls/my-test-slug")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["slug"] == "my-test-slug"


@pytest.mark.asyncio
async def test_poll_not_found(client):
    """Test that accessing a non-existent poll returns 404"""
    response = await client.get("/api/v1/polls/nonexistent")
    assert response.status_code == 404


# ==============================================================================
# POLL SETTINGS - TIES
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_allow_ties_true(create_poll):
    """Test creating a poll that allows ties"""
    poll = await create_poll(
        title="Allow Ties Poll",
        settings={"allow_ties": True}
    )
    
    assert poll["candidates"]  # Poll created successfully


@pytest.mark.asyncio
async def test_create_poll_allow_ties_false(create_poll):
    """Test creating a poll that does NOT allow ties"""
    poll = await create_poll(
        title="No Ties Poll",
        settings={"allow_ties": False}
    )
    
    assert poll["candidates"]  # Poll created successfully


# ==============================================================================
# POLL SETTINGS - RANKINGS
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_require_complete_ranking(create_poll):
    """Test poll that requires complete rankings"""
    poll = await create_poll(
        title="Complete Ranking Required",
        settings={"require_complete_ranking": True}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_partial_ranking_allowed(create_poll):
    """Test poll that allows partial rankings"""
    poll = await create_poll(
        title="Partial Ranking OK",
        settings={"require_complete_ranking": False}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_with_limited_ranks(create_poll):
    """Test poll with limited number of ranks (e.g., rank top 3 of 5)"""
    poll = await create_poll(
        title="Rank Your Top 3",
        candidates=[
            {"name": "A"}, {"name": "B"}, {"name": "C"},
            {"name": "D"}, {"name": "E"}
        ],
        settings={"num_ranks": 3}
    )
    
    assert len(poll["candidates"]) == 5


# ==============================================================================
# POLL SETTINGS - WRITE-INS
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_allow_write_ins(create_poll):
    """Test creating a poll that allows write-in candidates"""
    poll = await create_poll(
        title="Write-ins Allowed",
        settings={"allow_write_ins": True}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_no_write_ins(create_poll):
    """Test creating a poll that does NOT allow write-ins"""
    poll = await create_poll(
        title="No Write-ins",
        settings={"allow_write_ins": False}
    )
    
    assert poll["candidates"]


# ==============================================================================
# POLL SETTINGS - RANDOMIZATION
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_randomize_options(create_poll):
    """Test poll with randomized candidate order"""
    poll = await create_poll(
        title="Randomized Options",
        settings={"randomize_options": True}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_fixed_order(create_poll):
    """Test poll with fixed candidate order"""
    poll = await create_poll(
        title="Fixed Order",
        settings={"randomize_options": False}
    )
    
    assert poll["candidates"]


# ==============================================================================
# POLL SETTINGS - RESULTS VISIBILITY
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_results_public(create_poll):
    """Test poll with public results"""
    poll = await create_poll(
        title="Public Results",
        settings={"results_visibility": "public"}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_results_voters_only(create_poll):
    """Test poll with results visible to voters only"""
    poll = await create_poll(
        title="Voters Only Results",
        settings={"results_visibility": "voters"}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_results_owner_only(create_poll):
    """Test poll with results visible to owner only"""
    poll = await create_poll(
        title="Owner Only Results",
        settings={"results_visibility": "owner"}
    )
    
    assert poll["candidates"]


# ==============================================================================
# POLL SETTINGS - LIVE RESULTS
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_show_live_results(create_poll):
    """Test poll with live results enabled"""
    poll = await create_poll(
        title="Live Results",
        settings={"show_live_results": True}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_hide_live_results(create_poll):
    """Test poll with live results disabled"""
    poll = await create_poll(
        title="No Live Results",
        settings={"show_live_results": False}
    )
    
    assert poll["candidates"]


# ==============================================================================
# POLL SETTINGS - ANONYMIZATION
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_anonymize_voters(create_poll):
    """Test poll with voter anonymization"""
    poll = await create_poll(
        title="Anonymous Voting",
        settings={"anonymize_voters": True}
    )
    
    assert poll["candidates"]


@pytest.mark.asyncio
async def test_create_poll_public_voters(create_poll):
    """Test poll without voter anonymization"""
    poll = await create_poll(
        title="Public Voters",
        settings={"anonymize_voters": False}
    )
    
    assert poll["candidates"]


# ==============================================================================
# POLL SETTINGS - BALLOT PROCESSING
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_alaska_rule(create_poll):
    """Test poll with Alaska ballot processing rule"""
    poll = await create_poll(
        title="Alaska Rule Poll",
        settings={"ballot_processing_rule": "alaska"}
    )
    
    assert poll["candidates"]


# ==============================================================================
# PRIVATE POLLS
# ==============================================================================

@pytest.mark.asyncio
async def test_create_private_poll_with_voters(create_poll):
    """Test creating a private poll with voter list"""
    poll = await create_poll(
        title="Private Poll",
        is_private=True,
        voter_emails=[
            "voter1@example.com",
            "voter2@example.com",
            "voter3@example.com"
        ]
    )
    
    assert poll["voters_added"] == 3


@pytest.mark.asyncio
async def test_create_private_poll_without_voters(create_poll):
    """Test creating a private poll without initial voters"""
    poll = await create_poll(
        title="Private Poll No Voters",
        is_private=True
    )
    
    assert poll["voters_added"] == 0


# ==============================================================================
# COMPLEX SETTINGS COMBINATIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_complex_settings(create_poll):
    """Test poll with multiple settings combined"""
    poll = await create_poll(
        title="Complex Poll",
        candidates=[
            {"name": "Option A"},
            {"name": "Option B"},
            {"name": "Option C"},
            {"name": "Option D"}
        ],
        settings={
            "allow_ties": True,
            "require_complete_ranking": False,
            "allow_write_ins": True,
            "show_live_results": True,
            "results_visibility": "public",
            "num_ranks": 3
        }
    )
    
    assert len(poll["candidates"]) == 4


# ==============================================================================
# POLL SETTINGS - VOTE UPDATES
# ==============================================================================

@pytest.mark.asyncio
async def test_create_poll_allow_vote_updates_true(create_poll, client):
    """Test creating a poll that allows vote updates (default)"""
    poll = await create_poll(
        title="Vote Updates Allowed",
        settings={"allow_vote_updates": True}
    )
    
    # Fetch the poll to verify settings
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["settings"]["allow_vote_updates"] == True


@pytest.mark.asyncio
async def test_create_poll_allow_vote_updates_false(create_poll, client):
    """Test creating a poll that does NOT allow vote updates"""
    poll = await create_poll(
        title="Vote Updates Disabled",
        settings={"allow_vote_updates": False}
    )
    
    # Fetch the poll to verify settings
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["settings"]["allow_vote_updates"] == False


@pytest.mark.asyncio
async def test_create_poll_vote_updates_default(create_poll, client):
    """Test that allow_vote_updates defaults to True when not specified"""
    poll = await create_poll(
        title="Default Vote Updates",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    # Fetch the poll to verify settings default
    response = await client.get(f"/api/v1/polls/{poll['short_id']}")
    assert response.status_code == 200
    poll_data = response.json()
    # Should default to True (or not be present, which means True)
    assert poll_data["settings"].get("allow_vote_updates", True) == True
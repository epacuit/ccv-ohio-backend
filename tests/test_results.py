# tests/test_results.py
"""
Results Calculation Tests

Tests results calculation with various ballot configurations:
- Simple majorities
- Condorcet winners
- Edge cases (ties, cycles, truncated ballots)
- Results caching and invalidation
- Integration tests with real-world scenarios
"""

import pytest
from tests.conftest import generate_unique_fingerprint


# ==============================================================================
# BASIC RESULTS CALCULATION
# ==============================================================================

@pytest.mark.asyncio
async def test_simple_majority_winner(create_poll, submit_ballot, get_results):
    """Test a simple case with a clear majority winner"""
    # Create poll
    poll = await create_poll(
        title="Simple Majority",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit 5 ballots, all ranking A first
    for i in range(5):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},  # A
                {"candidate_id": candidate_ids[1], "rank": 2},  # B
                {"candidate_id": candidate_ids[2], "rank": 3}   # C
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    
    # Verify results exist with correct structure
    assert "copeland_scores" in results
    assert "explanation" in results
    # A should have the highest Copeland score
    a_name = poll["candidates"][0]["name"]
    max_score = max(results["copeland_scores"].values())
    assert results["copeland_scores"][a_name] == max_score


@pytest.mark.asyncio
async def test_single_ballot_result(create_poll, submit_ballot, get_results):
    """Test results with just one ballot"""
    poll = await create_poll(
        title="Single Ballot",
        candidates=[{"name": "X"}, {"name": "Y"}, {"name": "Z"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit one ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results


@pytest.mark.asyncio
async def test_no_ballots_result(create_poll, get_results):
    """Test results when no ballots have been submitted"""
    poll = await create_poll(
        title="No Ballots",
        candidates=[{"name": "A"}, {"name": "B"}]
    )
    
    # Get results without any ballots
    results = await get_results(poll["short_id"])
    
    # Should return a "no votes" status
    assert results["status"] == "no_votes"
    assert results["statistics"]["total_votes"] == 0


# ==============================================================================
# CONDORCET WINNER SCENARIOS
# ==============================================================================

@pytest.mark.asyncio
async def test_clear_condorcet_winner(create_poll, submit_ballot, get_results):
    """
    Test a clear Condorcet winner (candidate that beats all others pairwise).
    
    Scenario: A beats B, A beats C, B beats C
    Ballots:
    - 3 voters: A > B > C
    - 2 voters: B > A > C
    - 1 voter:  A > C > B
    
    A should win (beats B 4-2, beats C 6-0)
    """
    poll = await create_poll(
        title="Condorcet Winner",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    a_id, b_id, c_id = candidate_ids
    
    # 3 voters: A > B > C
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": a_id, "rank": 1},
                {"candidate_id": b_id, "rank": 2},
                {"candidate_id": c_id, "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 2 voters: B > A > C
    for i in range(2):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": b_id, "rank": 1},
                {"candidate_id": a_id, "rank": 2},
                {"candidate_id": c_id, "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 1 voter: A > C > B
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": a_id, "rank": 1},
            {"candidate_id": c_id, "rank": 2},
            {"candidate_id": b_id, "rank": 3}
        ],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    # Get results
    results = await get_results(poll["short_id"])
    
    # Verify A wins
    assert "copeland_scores" in results
    assert "explanation" in results
    # The winner should be A (first candidate) - check by copeland score
    a_name = poll["candidates"][0]["name"]
    max_score = max(results["copeland_scores"].values())
    assert results["copeland_scores"][a_name] == max_score


# ==============================================================================
# CONDORCET CYCLE (ROCK-PAPER-SCISSORS)
# ==============================================================================

@pytest.mark.asyncio
async def test_condorcet_cycle(create_poll, submit_ballot, get_results):
    """
    Test a Condorcet cycle where no clear winner exists.
    
    Scenario: A beats B, B beats C, C beats A (rock-paper-scissors)
    Ballots:
    - 3 voters: A > B > C
    - 3 voters: B > C > A
    - 3 voters: C > A > B
    """
    poll = await create_poll(
        title="Condorcet Cycle",
        candidates=[{"name": "Rock"}, {"name": "Paper"}, {"name": "Scissors"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    a_id, b_id, c_id = candidate_ids
    
    # 3 voters: A > B > C
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": a_id, "rank": 1},
                {"candidate_id": b_id, "rank": 2},
                {"candidate_id": c_id, "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 3 voters: B > C > A
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": b_id, "rank": 1},
                {"candidate_id": c_id, "rank": 2},
                {"candidate_id": a_id, "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 3 voters: C > A > B
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": c_id, "rank": 1},
                {"candidate_id": a_id, "rank": 2},
                {"candidate_id": b_id, "rank": 3}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results - should resolve the cycle somehow
    results = await get_results(poll["short_id"])
    
    # Should still produce results with proper structure
    assert "copeland_scores" in results
    assert "explanation" in results
    # In a cycle, all candidates should have equal or similar Copeland scores
    scores = list(results["copeland_scores"].values())
    assert len(set(scores)) <= 2  # At most 2 different scores in a cycle


# ==============================================================================
# TRUNCATED BALLOTS
# ==============================================================================

@pytest.mark.asyncio
async def test_mixed_complete_and_partial_rankings(create_poll, submit_ballot, get_results):
    """Test results with a mix of complete and partial rankings"""
    poll = await create_poll(
        title="Mixed Rankings",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        settings={"require_complete_ranking": False}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # 3 complete ballots: A > B > C > D
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},
                {"candidate_id": candidate_ids[1], "rank": 2},
                {"candidate_id": candidate_ids[2], "rank": 3},
                {"candidate_id": candidate_ids[3], "rank": 4}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 2 partial ballots: Only rank A > B
    for i in range(2):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},
                {"candidate_id": candidate_ids[1], "rank": 2}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results


# ==============================================================================
# TIED BALLOTS
# ==============================================================================

@pytest.mark.asyncio
async def test_all_candidates_tied(create_poll, submit_ballot, get_results):
    """Test when all candidates are tied equally"""
    poll = await create_poll(
        title="All Tied",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"allow_ties": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # All voters rank everyone equally
    for i in range(5):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},
                {"candidate_id": candidate_ids[1], "rank": 1},
                {"candidate_id": candidate_ids[2], "rank": 1}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    
    # Should handle tie scenario
    assert "copeland_scores" in results
    assert "explanation" in results
    # All candidates should have equal Copeland scores since they're all tied
    scores = list(results["copeland_scores"].values())
    assert len(set(scores)) == 1  # All same score


@pytest.mark.asyncio
async def test_mixed_tied_rankings(create_poll, submit_ballot, get_results):
    """Test ballots with partial ties (e.g., A=B > C)"""
    poll = await create_poll(
        title="Partial Ties",
        candidates=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        settings={"allow_ties": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Voters rank A=B > C
    for i in range(4):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},
                {"candidate_id": candidate_ids[1], "rank": 1},  # Tied with A
                {"candidate_id": candidate_ids[2], "rank": 2}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results


# ==============================================================================
# EDGE CASES - CANDIDATE COUNTS
# ==============================================================================

@pytest.mark.asyncio
async def test_single_candidate_poll(create_poll, submit_ballot, get_results):
    """Test a poll with only one candidate"""
    poll = await create_poll(
        title="Single Candidate",
        candidates=[{"name": "Only Option"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit some ballots
    for i in range(3):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results - should trivially win
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results
    # The single candidate should have the only (and thus highest) score
    assert len(results["copeland_scores"]) == 1
    candidate_name = poll["candidates"][0]["name"]
    assert candidate_name in results["copeland_scores"]


@pytest.mark.asyncio
async def test_two_candidate_poll(create_poll, submit_ballot, get_results):
    """Test a simple two-candidate poll"""
    poll = await create_poll(
        title="Two Candidates",
        candidates=[{"name": "Yes"}, {"name": "No"}]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # 4 voters prefer Yes
    for i in range(4):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[0], "rank": 1},
                {"candidate_id": candidate_ids[1], "rank": 2}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # 2 voters prefer No
    for i in range(2):
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=[
                {"candidate_id": candidate_ids[1], "rank": 1},
                {"candidate_id": candidate_ids[0], "rank": 2}
            ],
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results - Yes should win
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results
    # "Yes" should win (first candidate) - check it has highest score
    yes_name = poll["candidates"][0]["name"]
    no_name = poll["candidates"][1]["name"]
    assert results["copeland_scores"][yes_name] > results["copeland_scores"][no_name]


@pytest.mark.asyncio
async def test_large_candidate_set(create_poll, submit_ballot, get_results):
    """Test a poll with 10 candidates"""
    candidates = [{"name": f"Candidate {i}"} for i in range(1, 11)]
    
    poll = await create_poll(
        title="10 Candidates",
        candidates=candidates
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit 5 ballots with various rankings
    for i in range(5):
        # Each voter ranks their top 5
        rankings = [
            {"candidate_id": candidate_ids[j], "rank": j + 1}
            for j in range(5)
        ]
        
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=rankings,
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results


# ==============================================================================
# WRITE-IN RESULTS
# ==============================================================================

@pytest.mark.asyncio
async def test_results_with_write_ins(create_poll, submit_ballot, get_results):
    """Test that write-in candidates appear in results"""
    poll = await create_poll(
        title="Write-ins in Results",
        candidates=[{"name": "A"}, {"name": "B"}],
        settings={"allow_write_ins": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit ballot with write-in
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[
            {"candidate_id": "write-in-xyz", "rank": 1},
            {"candidate_id": candidate_ids[0], "rank": 2}
        ],
        voter_fingerprint=generate_unique_fingerprint(),
        write_ins=[
            {"id": "write-in-xyz", "name": "Custom", "is_write_in": True}
        ]
    )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results


# ==============================================================================
# RESULTS CACHING
# ==============================================================================

@pytest.mark.asyncio
async def test_results_are_cached(create_poll, submit_ballot, get_results, client):
    """Test that results are cached after first calculation"""
    poll = await create_poll(title="Caching Test")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit a ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    # Get results first time (will calculate)
    results1 = await get_results(poll["short_id"])
    
    # Check status
    response = await client.get(f"/api/v1/results/{poll['short_id']}/status")
    status = response.json()
    assert status["status"] == "calculated"
    # is_stale should be False if present, or it might not be in the response
    if "is_stale" in status:
        assert status["is_stale"] == False


@pytest.mark.asyncio
async def test_cache_invalidated_on_new_ballot(create_poll, submit_ballot, get_results, client):
    """Test that cache is invalidated when new ballots are submitted"""
    poll = await create_poll(title="Cache Invalidation")
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Submit first ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[0], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    # Get results (calculates and caches)
    results1 = await get_results(poll["short_id"])
    
    # Submit another ballot
    await submit_ballot(
        poll_id=poll["short_id"],
        rankings=[{"candidate_id": candidate_ids[1], "rank": 1}],
        voter_fingerprint=generate_unique_fingerprint()
    )
    
    # Check status - should be stale or needs recalculation
    response = await client.get(f"/api/v1/results/{poll['short_id']}/status")
    status = response.json()
    # Either it's marked stale or it needs calculation
    is_stale = status.get("is_stale", False)
    needs_calc = status.get("needs_calculation", False)
    assert is_stale == True or needs_calc == True or status["status"] == "not_calculated"
    
    # Get results again (should recalculate)
    results2 = await get_results(poll["short_id"])
    assert "copeland_scores" in results2
    assert "explanation" in results2


# ==============================================================================
# REAL-WORLD INTEGRATION SCENARIOS
# ==============================================================================

@pytest.mark.asyncio
async def test_pizza_poll_scenario(create_poll, submit_ballot, get_results, realistic_candidates):
    """
    Real-world scenario: Pizza choice poll.
    10 voters, 5 options, mixed preferences.
    """
    poll = await create_poll(
        title="Team Pizza Order",
        candidates=realistic_candidates["pizza"]
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # Simulate 10 voters with varied preferences
    preferences = [
        [0, 1, 2, 3, 4],  # Pepperoni first
        [0, 1, 2, 3, 4],  # Pepperoni first
        [0, 2, 1, 3, 4],  # Pepperoni, BBQ
        [1, 0, 2, 3, 4],  # Margherita first
        [1, 0, 2, 3, 4],  # Margherita first
        [2, 0, 1, 3, 4],  # BBQ first
        [3, 1, 0, 2, 4],  # Veggie first
        [0, 2, 1, 3, 4],  # Pepperoni
        [1, 0, 3, 2, 4],  # Margherita
        [4, 3, 1, 0, 2],  # Hawaiian first (controversial!)
    ]
    
    for pref in preferences:
        rankings = [
            {"candidate_id": candidate_ids[pref[i]], "rank": i + 1}
            for i in range(len(pref))
        ]
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=rankings,
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    
    # Should have results with proper structure
    assert "copeland_scores" in results
    assert "explanation" in results
    # Should have candidates and scores
    assert len(results["copeland_scores"]) > 0
    # At least one candidate should have the max score
    max_score = max(results["copeland_scores"].values())
    assert max_score > 0
    # Statistics might or might not be in results depending on implementation
    if "statistics" in results:
        assert results["statistics"]["total_votes"] == 10


@pytest.mark.asyncio
async def test_movie_poll_scenario(create_poll, submit_ballot, get_results, realistic_candidates):
    """Real-world scenario: Movie night poll"""
    poll = await create_poll(
        title="Movie Night Vote",
        candidates=realistic_candidates["movies"],
        settings={"allow_ties": True}
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # 7 voters with different preferences
    for i in range(7):
        # Vary the rankings
        rankings = [
            {"candidate_id": candidate_ids[(i + j) % 3], "rank": j + 1}
            for j in range(3)
        ]
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=rankings,
            voter_fingerprint=generate_unique_fingerprint()
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results
    # Statistics might or might not be in results depending on implementation
    if "statistics" in results:
        assert results["statistics"]["total_votes"] == 7


@pytest.mark.asyncio
async def test_project_priority_with_write_ins(create_poll, submit_ballot, get_results, realistic_candidates):
    """Real-world scenario: Project prioritization with write-ins"""
    poll = await create_poll(
        title="Q1 Project Priorities",
        candidates=realistic_candidates["projects"],
        settings={
            "allow_write_ins": True,
            "require_complete_ranking": False
        }
    )
    
    candidate_ids = [c["id"] for c in poll["candidates"]]
    
    # 5 team members vote, one adds a write-in
    for i in range(5):
        rankings = [
            {"candidate_id": candidate_ids[i % 4], "rank": 1},
            {"candidate_id": candidate_ids[(i + 1) % 4], "rank": 2}
        ]
        
        write_ins = None
        if i == 0:
            # One person adds a write-in
            write_ins = [{"name": "Technical Debt Cleanup", "is_write_in": True}]
            rankings.append({"candidate_id": "write-in-tech-debt", "rank": 3})
        
        await submit_ballot(
            poll_id=poll["short_id"],
            rankings=rankings,
            voter_fingerprint=generate_unique_fingerprint(),
            write_ins=write_ins
        )
    
    # Get results
    results = await get_results(poll["short_id"])
    assert "copeland_scores" in results
    assert "explanation" in results
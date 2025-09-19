# app/tests/test_csv_edge_cases.py
import asyncio
import httpx
from pathlib import Path

BASE_URL = "http://localhost:8000"

async def test_csv_profile(filename: str, description: str, winner_type: str, winning_set: list):
    """Test a specific CSV profile using bulk-import like an owner would"""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        print(f"\n📊 Testing: {description}")
        print(f"File: {filename}")
        
        # Read CSV
        csv_path = Path(f"../ccv-sample-polls/test_polls/{filename}")
        csv_content = csv_path.read_text()
        
        # Parse CSV to get candidates and ballots
        from app.services.csv_import import parse_csv_ballots
        candidates, ballots_data = parse_csv_ballots(csv_content)
        
        # 1. Create poll (what owner does first)
        poll_data = {
            "title": description,
            "candidates": candidates,
            "owner_email": "test@example.com"
        }
        response = await client.post(f"{BASE_URL}/api/v1/polls/", json=poll_data)
        poll = response.json()
        poll_id = poll['id']
        admin_token = poll['admin_token']
        print(f"Created poll: {poll['short_id']}")
        
        # 2. Bulk import ballots (what owner does when uploading CSV)
        import_data = {
            "poll_id": poll_id,
            "admin_token": admin_token,
            "ballots": ballots_data
        }
        response = await client.post(
            f"{BASE_URL}/api/v1/ballots/bulk-import",
            json=import_data
        )
        import_result = response.json()
        print(f"Imported: {import_result['total_votes']} votes in {import_result['unique_patterns']} patterns")
        
        # 3. Calculate results
        response = await client.post(
            f"{BASE_URL}/api/v1/results/calculate/{poll_id}",
            params={"admin_token": admin_token}
        )
        
        # 4. Get and display results
        response = await client.get(f"{BASE_URL}/api/v1/results/{poll_id}")
        results = response.json()
        
        print(f"Winner type: {results.get('winner_type')}")
        if 'winner' in results:
            print(f"Winner: {results['winner']}")
        elif 'winners' in results:
            print(f"Winners (tie): {results['winners']}")
        
        assert set(results.get('winners', [results.get('winner')])) == set(winning_set), f"Expected winners {winning_set}, got {results.get('winners', [results.get('winner')])}"
        if 'explanation' in results:
            exp = results['explanation']
            if exp['type'] == 'condorcet':
                print(f"  ✓ Beats all others head-to-head")
            elif exp['type'] == 'tie':
                print(f"  ✓ {len(results['winners'])} candidates tied")
                if winner_type != 'tie':
                    print(f"    (Expected winner type was {winner_type})")
            elif exp['type'] == 'most_wins':
                print(f"  ✓ Has {exp['max_wins']} wins (most)")
            elif exp['type'] == 'smallest_loss':
                print(f"  ✓ Smallest loss among those tied for most wins")

        # Validate winner type
        assert results.get('winner_type') == winner_type, f"Expected winner type {winner_type}, got {results.get('winner_type')}"
# ADD THIS MISSING FUNCTION:
async def run_all_tests():
    test_cases = [
        ("condorcet_paradox.csv", "Condorcet Paradox", "tie", ["A", "B", "C"]),
        ("unanimous.csv", "Unanimous Winner", "condorcet", ["A"]),
        ("plurality_winner.csv", "All Bullet Votes", "condorcet", ["A"]),
        ("maximum_wins.csv", "No Condorcet, One Copeland", "most_wins", ["B"]),
        ("minimum_loss.csv", "No Condorcet, Multiple Copeland, Minimum Loss", "smallest_loss", ["C"]),

        ("ties.csv", "No Condorcet, Ties", "tie", ["A", "B", "D"]),
        # ("unanimous.csv", "Unanimous Winner"),
        # ("tie_for_first.csv", "Two-way Tie"),
        # ("incomplete_rankings.csv", "Incomplete Rankings"),
        # ("with_ties_in_rankings.csv", "Rankings with Ties"),
    ]
    
    for filename, description, winner_type, winning_set in test_cases:
        await test_csv_profile(filename, description, winner_type, winning_set)

if __name__ == "__main__":
    asyncio.run(run_all_tests())

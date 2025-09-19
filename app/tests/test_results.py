# app/tests/test_results.py
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"

async def test_results_calculation():
    async with httpx.AsyncClient(follow_redirects=True) as client:
        print("🗳️ Testing Results Calculation\n")
        
        # 1. Create a poll
        poll_data = {
            "title": "Test MWSL Calculation",
            "candidates": [
                {"id": "A", "name": "Alice"},
                {"id": "B", "name": "Bob"},
                {"id": "C", "name": "Charlie"}
            ]
        }
        
        response = await client.post(f"{BASE_URL}/api/v1/polls/", json=poll_data)
        poll = response.json()
        poll_id = poll['id']
        admin_token = poll['admin_token']
        print(f"✅ Created poll: {poll['short_id']}\n")
        
        # 2. Submit some ballots (no Condorcet winner scenario)
        ballots = [
            {"poll_id": poll_id, "rankings": [{"candidate_id": "A", "rank": 1}, {"candidate_id": "B", "rank": 2}, {"candidate_id": "C", "rank": 3}], "voter_fingerprint": "v1"},
            {"poll_id": poll_id, "rankings": [{"candidate_id": "B", "rank": 1}, {"candidate_id": "C", "rank": 2}, {"candidate_id": "A", "rank": 3}], "voter_fingerprint": "v2"},
            {"poll_id": poll_id, "rankings": [{"candidate_id": "C", "rank": 1}, {"candidate_id": "A", "rank": 2}, {"candidate_id": "B", "rank": 3}], "voter_fingerprint": "v3"},
        ]
        
        for ballot in ballots:
            await client.post(f"{BASE_URL}/api/v1/ballots/", json=ballot)
        print("✅ Submitted 3 ballots (Condorcet paradox scenario)\n")
        
        # 3. Calculate results
        response = await client.post(
            f"{BASE_URL}/api/v1/results/calculate/{poll_id}",
            params={"admin_token": admin_token}
        )
        results = response.json()
        print(f"✅ Results calculated in {results.get('computation_time_ms', 0)}ms\n")
        
        # 4. Get results
        response = await client.get(f"{BASE_URL}/api/v1/results/{poll_id}")
        final_results = response.json()
        
        print("📊 Results:")
        print(f"Winner type: {final_results.get('winner_type')}")
        if 'winner' in final_results:
            print(f"Winner: {final_results['winner']}")
        else:
            print(f"Winners (tie): {final_results.get('winners')}")
        
        print(f"\nStatistics: {json.dumps(final_results.get('statistics'), indent=2)}")

if __name__ == "__main__":
    asyncio.run(test_results_calculation())

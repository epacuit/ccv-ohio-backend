# app/tests/test_api.py
import asyncio
import httpx
import json
from datetime import datetime, timezone, timedelta

BASE_URL = "http://localhost:8000"

async def test_api():
    async with httpx.AsyncClient(follow_redirects=True) as client:
        print("🧪 Testing CCV API...\n")
        
        # Test 1: Health check
        print("1️⃣ Testing health endpoint...")
        response = await client.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        print(f"✅ Health check: {response.json()}\n")
        
        # Test 2: Create poll
        print("2️⃣ Creating a poll...")
        poll_data = {
            "title": "Best Programming Language",
            "description": "Vote for your favorite",
            "candidates": [
                {"id": "py", "name": "Python"},
                {"id": "js", "name": "JavaScript"},
                {"id": "rust", "name": "Rust"}
            ],
            "settings": {
                "allow_ties": True,
                "require_complete_ranking": False
            },
            "owner_email": "test@example.com"
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/polls",
            json=poll_data
        )
        assert response.status_code == 200
        poll_response = response.json()
        print(f"✅ Created poll: {poll_response['short_id']}")
        print(f"   Admin token: {poll_response['admin_token']}\n")
        
        poll_id = poll_response['id']
        short_id = poll_response['short_id']
        admin_token = poll_response['admin_token']
        
        # Test 3: Get poll
        print("3️⃣ Getting poll by short_id...")
        response = await client.get(f"{BASE_URL}/api/v1/polls/{short_id}")
        assert response.status_code == 200
        poll = response.json()
        print(f"✅ Retrieved poll: {poll['title']}\n")
        
        # Test 4: Submit ballot
        print("4️⃣ Submitting a ballot...")
        ballot_data = {
            "poll_id": poll_id,
            "rankings": [
                {"candidate_id": "py", "rank": 1},
                {"candidate_id": "rust", "rank": 2},
                {"candidate_id": "js", "rank": 2}  # Tie!
            ],
            "voter_fingerprint": "test_user_123",
            "ip_address": "127.0.0.1"
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/ballots",
            json=ballot_data
        )
        assert response.status_code == 200
        ballot_response = response.json()
        print(f"✅ Ballot submitted: {ballot_response['message']}\n")
        
        # Test 5: Update ballot (same voter)
        print("5️⃣ Updating the ballot...")
        ballot_data['rankings'] = [
            {"candidate_id": "rust", "rank": 1},  # Changed mind!
            {"candidate_id": "py", "rank": 2},
            {"candidate_id": "js", "rank": 3}
        ]
        
        response = await client.post(
            f"{BASE_URL}/api/v1/ballots",
            json=ballot_data
        )
        assert response.status_code == 200
        update_response = response.json()
        print(f"✅ Ballot updated: {update_response['message']}\n")
        
        # Test 6: Get ballots (admin)
        print("6️⃣ Getting all ballots (admin)...")
        response = await client.get(
            f"{BASE_URL}/api/v1/ballots/poll/{poll_id}",
            params={"admin_token": admin_token}
        )
        assert response.status_code == 200
        ballots = response.json()
        print(f"✅ Retrieved {len(ballots)} ballot(s)")
        for b in ballots:
            print(f"   Ballot: {b['rankings']}, Count: {b['count']}\n")
        
        # Test 7: Get polls by owner
        print("7️⃣ Getting polls by owner...")
        response = await client.get(
            f"{BASE_URL}/api/v1/polls/by-owner",
            params={"email": "test@example.com"}
        )
        assert response.status_code == 200
        owner_polls = response.json()
        print(f"✅ Found {len(owner_polls)} poll(s) for owner")
        for p in owner_polls:
            print(f"   Poll: {p['title']}, Ballots: {p['total_ballots']}\n")
        
        # Test 8: Close poll
        print("8️⃣ Closing the poll...")
        response = await client.post(
            f"{BASE_URL}/api/v1/polls/{poll_id}/close",
            params={"admin_token": admin_token}
        )
        assert response.status_code == 200
        print(f"✅ Poll closed\n")
        
        # Test 9: Try to vote on closed poll
        print("9️⃣ Testing voting on closed poll...")
        response = await client.post(
            f"{BASE_URL}/api/v1/ballots",
            json=ballot_data
        )
        assert response.status_code == 200
        closed_response = response.json()
        assert closed_response['success'] == False
        print(f"✅ Correctly rejected: {closed_response['message']}\n")
        
        print("🎉 All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_api())
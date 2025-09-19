import asyncio
import httpx

async def debug_owner():
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Try the endpoint
        response = await client.get(
            "http://localhost:8000/api/v1/polls/by-owner",
            params={"email": "test@example.com"}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

asyncio.run(debug_owner())
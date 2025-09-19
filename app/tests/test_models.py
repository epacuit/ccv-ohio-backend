# app/tests/test_models.py
import asyncio
import secrets
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Import your models
from app.models import Base, Poll, Ballot, Result
from app.models.poll_settings import DEFAULT_SETTINGS

load_dotenv()

# Test database URL (using your local Docker PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ccv_user:ccv_pass@localhost:5432/ccv_db")

async def test_models():
    """Test that models work correctly"""
    
    # Create engine
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    # Create session
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with engine.begin() as conn:
        # Drop all tables (clean slate for testing)
        await conn.run_sync(Base.metadata.drop_all)
        print("✅ Dropped all tables")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Created all tables")
    
    async with async_session() as session:
        # Test 1: Create a Poll
        print("\n📋 Testing Poll creation...")
        poll = Poll(
            short_id="test123",
            title="Test Ice Cream Poll",
            description="What's your favorite flavor?",
            is_private=False,
            status='open',
            closing_at=datetime.utcnow() + timedelta(days=7),
            candidates=[
                {"id": "cand1", "name": "Vanilla", "long_name": "French Vanilla"},
                {"id": "cand2", "name": "Chocolate", "description": "Dark chocolate"},
                {"id": "cand3", "name": "Strawberry"}
            ],
            settings=DEFAULT_SETTINGS,
            owner_email="test@example.com",
            admin_token=secrets.token_urlsafe(32)
        )
        
        session.add(poll)
        await session.commit()
        print(f"✅ Created poll with ID: {poll.id}")
        
        # Test 2: Create a Ballot
        print("\n🗳️ Testing Ballot creation...")
        ballot = Ballot(
            poll_id=poll.id,
            rankings=[
                {"candidate_id": "cand1", "rank": 1},
                {"candidate_id": "cand2", "rank": 2},
                {"candidate_id": "cand3", "rank": 2}  # Tie!
            ],
            count=1,
            voter_fingerprint="test_fingerprint_hash",
            ip_hash="test_ip_hash"
        )
        
        session.add(ballot)
        await session.commit()
        print(f"✅ Created ballot with ID: {ballot.id}")
        
        # Test 3: Create a Result
        print("\n📊 Testing Result creation...")
        result = Result(
            poll_id=poll.id,
            data={
                "winner": "Vanilla",
                "winner_type": "most_wins",
                "total_ballots": 1
            },
            computation_time_ms=42,
            is_current=True
        )
        
        session.add(result)
        await session.commit()
        print(f"✅ Created result with ID: {result.id}")
        
        # Test 4: Query tests
        print("\n🔍 Testing queries...")
        
        # Query poll by short_id
        from sqlalchemy import select
        stmt = select(Poll).where(Poll.short_id == "test123")
        result = await session.execute(stmt)
        found_poll = result.scalar_one_or_none()
        assert found_poll is not None
        print(f"✅ Found poll by short_id: {found_poll.title}")
        
        # Query ballots for poll
        stmt = select(Ballot).where(Ballot.poll_id == poll.id)
        result = await session.execute(stmt)
        ballots = result.scalars().all()
        print(f"✅ Found {len(ballots)} ballot(s) for poll")
        
        # Test JSONB access
        print(f"✅ Poll settings allow_ties: {poll.settings.get('allow_ties')}")
        print(f"✅ First candidate name: {poll.candidates[0]['name']}")
        
    await engine.dispose()
    print("\n🎉 All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_models())
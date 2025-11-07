# tests/conftest.py
"""
Test Configuration and Fixtures

This file sets up:
1. Test database connection (using your local PostgreSQL database)
2. Reusable fixtures for creating polls, candidates, and ballots
3. Automatic cleanup after tests (deletes test data)
"""

import pytest
import asyncio
import os
from typing import AsyncGenerator, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from dotenv import load_dotenv

# CRITICAL: Force DEV_MODE to false BEFORE loading .env or importing modules
# This ensures all tests run in production mode, even if .env has DEV_MODE=true
os.environ['DEV_MODE'] = 'false'

# Load environment variables from .env file
# (DEV_MODE won't be overridden because we already set it above)
load_dotenv()

# Import your app and models
from app.main import app
from app.models.base import Base
from app.db import get_db


# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================

# Use your local database for testing - loaded from .env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL not found! Make sure you have a .env file with:\n"
        "DATABASE_URL=postgresql+asyncpg://ccv_user:ccv_pass@localhost:5432/ccv_db"
    )

# Create async engine for tests with proper configuration
# NullPool disables connection pooling to avoid conflicts between tests
from sqlalchemy.pool import NullPool

test_engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    poolclass=NullPool,  # Disable connection pooling for tests
)

TestSessionLocal = async_sessionmaker(
    test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False,
)


# ==============================================================================
# SESSION FIXTURES
# ==============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provides an HTTP client for making API requests.
    Each request gets its own database session to avoid connection conflicts.
    """
    async def override_get_db():
        """Each request gets a fresh session"""
        async with TestSessionLocal() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()
    
    # Cleanup after test completes: Delete all test polls
    async with TestSessionLocal() as cleanup_session:
        await cleanup_session.execute(text("DELETE FROM polls WHERE is_test = true"))
        await cleanup_session.commit()


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a standalone database session for tests that need direct DB access.
    This is separate from the sessions used by the API client.
    """
    async with TestSessionLocal() as session:
        yield session


# ==============================================================================
# HELPER FIXTURES - CANDIDATE CREATION
# ==============================================================================

@pytest.fixture
def sample_candidates():
    """Returns a function that creates candidate lists"""
    def _create_candidates(count: int = 3, prefix: str = "Candidate") -> List[Dict[str, Any]]:
        """
        Create a list of candidates.
        
        Args:
            count: Number of candidates to create
            prefix: Name prefix (e.g., "Candidate" -> "Candidate A", "Candidate B")
        
        Returns:
            List of candidate dicts with name and description
        """
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return [
            {
                "name": f"{prefix} {letters[i]}",
                "description": f"Description for {prefix} {letters[i]}"
            }
            for i in range(count)
        ]
    return _create_candidates


@pytest.fixture
def realistic_candidates():
    """Returns common real-world candidate sets for testing"""
    return {
        "pizza": [
            {"name": "Pepperoni", "description": "Classic pepperoni pizza"},
            {"name": "Margherita", "description": "Fresh mozzarella and basil"},
            {"name": "BBQ Chicken", "description": "BBQ sauce with grilled chicken"},
            {"name": "Veggie Supreme", "description": "Loaded with fresh vegetables"},
            {"name": "Hawaiian", "description": "Ham and pineapple"}
        ],
        "movies": [
            {"name": "The Shawshank Redemption", "description": "Drama about hope"},
            {"name": "The Godfather", "description": "Classic crime saga"},
            {"name": "The Dark Knight", "description": "Batman vs Joker"}
        ],
        "projects": [
            {"name": "Mobile App Redesign", "description": "Update UI/UX"},
            {"name": "API Performance", "description": "Optimize backend"},
            {"name": "New Feature: Comments", "description": "Add comment system"},
            {"name": "Security Audit", "description": "Review and fix issues"}
        ]
    }


# ==============================================================================
# HELPER FIXTURES - POLL CREATION
# ==============================================================================

@pytest.fixture
def create_poll(client: AsyncClient):
    """
    Returns a function that creates polls with various settings.
    Automatically marks polls as test polls for cleanup.
    """
    async def _create_poll(
        title: str = "Test Poll",
        candidates: List[Dict[str, Any]] = None,
        settings: Dict[str, Any] = None,
        slug: str = None,
        is_private: bool = False,
        voter_emails: List[str] = None
    ) -> Dict[str, Any]:
        """
        Create a poll via the API.
        
        Args:
            title: Poll title
            candidates: List of candidate dicts
            settings: Poll settings dict
            slug: Custom slug (optional)
            is_private: Whether poll is private
            voter_emails: List of voter emails for private polls
        
        Returns:
            API response with poll data
        """
        if candidates is None:
            candidates = [
                {"name": "Option A"},
                {"name": "Option B"},
                {"name": "Option C"}
            ]
        
        poll_data = {
            "title": title,
            "candidates": candidates,
            "settings": settings or {},
            "is_test": True,  # CRITICAL: Mark as test for cleanup
            "is_private": is_private
        }
        
        if slug:
            poll_data["slug"] = slug
            poll_data["owner_email"] = "test@example.com"  # Required for slugs
        
        if is_private and voter_emails:
            poll_data["voter_emails"] = voter_emails
        
        response = await client.post("/api/v1/polls/", json=poll_data)
        assert response.status_code == 200, f"Failed to create poll: {response.text}"
        return response.json()
    
    return _create_poll


# ==============================================================================
# HELPER FIXTURES - BALLOT SUBMISSION
# ==============================================================================

@pytest.fixture
def submit_ballot(client: AsyncClient):
    """Returns a function that submits ballots to polls"""
    async def _submit_ballot(
        poll_id: str,
        rankings: List[Dict[str, Any]],
        voter_fingerprint: str = None,
        voter_token: str = None,
        write_ins: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit a ballot to a poll.
        
        Args:
            poll_id: Poll ID (UUID, short_id, or slug)
            rankings: List of {"candidate_id": "...", "rank": 1} dicts
            voter_fingerprint: Unique voter identifier (for public polls)
            voter_token: Voter token (for private polls)
            write_ins: Optional list of write-in candidates
        
        Returns:
            API response with ballot data
        """
        ballot_data = {
            "poll_id": poll_id,
            "rankings": rankings,
            "is_test": True
        }
        
        if voter_fingerprint:
            ballot_data["voter_fingerprint"] = voter_fingerprint
        
        if voter_token:
            ballot_data["voter_token"] = voter_token
        
        if write_ins:
            ballot_data["write_ins"] = write_ins
        
        response = await client.post("/api/v1/ballots/", json=ballot_data)
        return response
    
    return _submit_ballot


# ==============================================================================
# HELPER FIXTURES - RESULT CHECKING
# ==============================================================================

@pytest.fixture
def get_results(client: AsyncClient):
    """Returns a function that fetches results for a poll"""
    async def _get_results(poll_id: str) -> Dict[str, Any]:
        """
        Get results for a poll.
        
        Args:
            poll_id: Poll ID (UUID, short_id, or slug)
        
        Returns:
            Results data
        """
        response = await client.get(f"/api/v1/results/{poll_id}")
        assert response.status_code == 200, f"Failed to get results: {response.text}"
        return response.json()
    
    return _get_results


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def generate_unique_fingerprint() -> str:
    """Generate a unique voter fingerprint for testing"""
    return f"test-fingerprint-{uuid4().hex[:16]}"


def generate_unique_email() -> str:
    """Generate a unique email for testing"""
    return f"test-{uuid4().hex[:8]}@example.com"


# ==============================================================================
# CLEANUP
# ==============================================================================
# Note: Cleanup happens automatically in the client fixture after each test

@pytest.fixture(scope="session", autouse=True)
async def cleanup_engine():
    """Dispose of the database engine after all tests complete"""
    yield
    await test_engine.dispose()
    print("\n✅ Database engine disposed")
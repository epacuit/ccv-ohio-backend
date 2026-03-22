# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import logging
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Import routers
from app.api.v1 import polls, ballots, results, exports, voters, demo, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting CCV Backend...")
    yield
    print("Shutting down CCV Backend...")

app = FastAPI(
    title="CCV Backend",
    description="Consensus Choice API",
    version="1.0.0",
    lifespan=lifespan
)

# Attach limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "https://ccv-app.netlify.app",
        "https://app.betterchoicesohio.org"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(polls.router, prefix="/api/v1/polls", tags=["polls"])
app.include_router(ballots.router, prefix="/api/v1/ballots", tags=["ballots"])
app.include_router(results.router, prefix="/api/v1/results", tags=["results"])
app.include_router(exports.router, prefix="/api/v1/exports", tags=["exports"])
app.include_router(voters.router, prefix="/api/v1", tags=["voters"])
app.include_router(demo.router, prefix="/api/v1/demo", tags=["demo"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "CCV Backend"}

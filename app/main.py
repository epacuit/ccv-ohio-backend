# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routers
from app.api.v1 import polls, ballots, results

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting CCV Backend...")
    yield
    print("Shutting down CCV Backend...")

app = FastAPI(
    title="CCV Backend",
    description="Consensus Choice Voting API",
    version="1.0.0",
    lifespan=lifespan
)

# Add request logging middleware BEFORE CORS
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming {request.method} {request.url.path}")
    logger.info(f"Origin header: {request.headers.get('origin', 'None')}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(polls.router, prefix="/api/v1/polls", tags=["polls"])
app.include_router(ballots.router, prefix="/api/v1/ballots", tags=["ballots"])
app.include_router(results.router, prefix="/api/v1/results", tags=["results"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "CCV Backend"}
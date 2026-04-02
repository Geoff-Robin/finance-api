"""
Zorvyn financial data backend main execution block bridging configuration, lifecycle events, and routes.
"""
from fastapi import FastAPI, Request
from async_fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from pydantic import BaseModel
from models import Base
from routers import auth, financial, users
from dependencies import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from typing import Any
import os

load_dotenv()

class Settings(BaseModel):
    """
    Configuration payload used dynamically by the AuthJWT module.
    """
    authjwt_secret_key: str

DATABASE_URL = os.environ["DATABASE_URL"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Orchestrates application startup/shutdown processes.
    Creates tables via SQLAlchemy and caches the asynchronous SessionLocal scope.

    Args:
        app (FastAPI): The currently active FastAPI application.
    """
    engine = create_async_engine(
        DATABASE_URL,
        echo=True
    )
    SessionLocal = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database Connection Ready")
    yield
    await engine.dispose()
    print("DB closed")

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@AuthJWT.load_config
def get_config() -> Any:
    """
    Feeds the JWT secret settings dynamically to AuthJWT.

    Returns:
        Any: Standard settings object with nested payload configurations.
    """
    return Settings(authjwt_secret_key=os.environ["JWT_SECRET_KEY"])

# Include Routers
app.include_router(auth.router)
app.include_router(financial.router)
app.include_router(users.router)

@app.get("/")
async def root():
    """
    Standard heartbeat or landing endpoint mapping to default routing.

    Returns:
        dict: Standard heartbeat response.
    """
    return {"message": "Zorvyn Financial Backend API"}

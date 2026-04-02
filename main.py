"""
Zorvyn financial data backend — application entry point.

Configures the FastAPI instance with rich OpenAPI metadata, registers all
routers, wires up the async database lifecycle, and attaches rate-limiting.
"""
from fastapi import FastAPI, Request
from async_fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
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

TAGS_METADATA = [
    {
        "name": "Authentication",
        "description": (
            "Endpoints for **user registration** and **login**.\n\n"
            "- `POST /register` — create a new account with a role.\n"
            "- `POST /login` — exchange credentials for a **Bearer JWT** that "
            "must be passed in the `Authorization` header of every protected route.\n\n"
            "> ⚠️ Both endpoints are rate-limited to **5 requests / minute** per IP."
        ),
    },
    {
        "name": "User Management",
        "description": (
            "Admin-only endpoints for **managing user accounts**.\n\n"
            "| Role | List users | Get user | Update role | Toggle status |\n"
            "|------|-----------|---------|------------|---------------|\n"
            "| Admin | ✅ | ✅ | ✅ | ✅ |\n"
            "| Analyst | ❌ | ❌ | ❌ | ❌ |\n"
            "| Viewer | ❌ | ❌ | ❌ | ❌ |\n\n"
            "Deactivating a user immediately blocks their JWT from being accepted "
            "on all protected endpoints."
        ),
    },
    {
        "name": "Financial Records",
        "description": (
            "Core CRUD and analytics endpoints for **financial records**.\n\n"
            "### Role-Permission Matrix\n\n"
            "| Action | Admin | Analyst | Viewer |\n"
            "|--------|-------|---------|--------|\n"
            "| Create record | ✅ | ❌ | ❌ |\n"
            "| List records | ✅ | ✅ | ❌ |\n"
            "| Get single record | ✅ | ✅ | ❌ |\n"
            "| Update record | ✅ | ❌ | ❌ |\n"
            "| Delete record (soft) | ✅ | ❌ | ❌ |\n"
            "| Dashboard summary | ✅ | ✅ | ✅ |\n\n"
            "### Soft Delete\n"
            "Records are **never permanently removed**. Deletion sets `is_deleted=True`, "
            "hiding the record from all listings and aggregations while preserving "
            "it for audit purposes.\n\n"
            "### Search\n"
            "Use the `?search=` query parameter for **case-insensitive partial matching** "
            "across both `category` and `notes` fields simultaneously."
        ),
    },
]



class Settings(BaseModel):
    """Configuration payload consumed dynamically by async-fastapi-jwt-auth."""
    authjwt_secret_key: str

DATABASE_URL = os.environ["DATABASE_URL"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    On startup: creates the async SQLAlchemy engine, initialises all database
    tables (idempotent), and stores the session factory on ``app.state``.
    On shutdown: disposes the connection pool cleanly.

    Args:
        app (FastAPI): The running FastAPI application instance.
    """
    engine = create_async_engine(DATABASE_URL, echo=True)
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



app = FastAPI(
    lifespan=lifespan,
    title="Zorvyn Financial API",
    version="1.0.0",
    summary="Secure, role-based financial data management backend.",
    description=(
        "## Overview\n"
        "**Zorvyn** is a production-ready REST API for managing personal or "
        "organisational financial records. It supports full CRUD operations, "
        "role-based access control, dashboard summaries, fuzzy search, and "
        "per-endpoint rate limiting.\n\n"
        "## Authentication\n"
        "All protected endpoints require a **Bearer JWT** in the `Authorization` "
        "header:\n"
        "```\nAuthorization: Bearer <token>\n```\n"
        "Obtain a token from `POST /login`.\n\n"
        "## Roles\n"
        "| Role | Description |\n"
        "|------|-------------|\n"
        "| `admin` | Full access — CRUD, user management, dashboard |\n"
        "| `analyst` | Read records, view dashboard insights |\n"
        "| `viewer` | Dashboard summary only |\n\n"
        "## Rate Limits\n"
        "| Endpoint group | Limit |\n"
        "|---------------|-------|\n"
        "| `/register`, `/login` | 5 / minute |\n"
        "| `POST / PATCH / DELETE /financial-records/` | 30 / minute |\n"
        "| `GET /financial-records/summary` | 60 / minute |\n"
        "| `GET /financial-records/` | 100 / minute |\n"
        "| `/users/` endpoints | 30–60 / minute |\n\n"
        "Exceeding a limit returns **`429 Too Many Requests`**.\n\n"
        "## Error Responses\n"
        "All errors follow the standard FastAPI envelope:\n"
        "```json\n{ \"detail\": \"Human-readable message\" }\n```"
    ),
    contact={
        "name": "Zorvyn API Support",
        "url": "https://github.com/Geoff-Robin/finance-api",
        "email": "support@zorvyn.dev",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@AuthJWT.load_config
def get_config() -> Any:
    """
    Supply the JWT secret key to async-fastapi-jwt-auth at runtime.

    Returns:
        Settings: Pydantic model carrying ``authjwt_secret_key``.
    """
    return Settings(authjwt_secret_key=os.environ["JWT_SECRET_KEY"])

# Include Routers
app.include_router(auth.router)
app.include_router(financial.router)
app.include_router(users.router)


@app.get(
    "/",
    summary="Health check",
    description="Returns a simple acknowledgement confirming the API is running.",
    tags=["Health"],
    response_description="API heartbeat message.",
    responses={200: {"content": {"application/json": {"example": {"message": "Zorvyn Financial Backend API"}}}}},
)
async def root():
    """
    Health-check / landing endpoint.

    Returns:
        dict: Static heartbeat payload.
    """
    return {"message": "Zorvyn Financial Backend API"}

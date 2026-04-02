"""
Financial records router — core CRUD, filtering, search, and dashboard summary.

Rate limits:
    POST /         30 / minute
    GET  /        100 / minute
    GET  /summary  60 / minute
    GET  /{id}    100 / minute
    PATCH /{id}    30 / minute
    DELETE /{id}   30 / minute
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import (
    FinancialRecordCreate,
    FinancialRecordRead,
    FinancialRecordUpdate,
    DashboardSummary,
    UserRole,
)
from models import FinancialType
from financial_dal import FinancialRecordDAL
from dependencies import get_db, RoleChecker, limiter
from typing import Any
from datetime import date

router = APIRouter(prefix="/financial-records", tags=["Financial Records"])

_AUTH_ERRORS = {
    401: {"description": "Missing or invalid Authorization header / expired JWT."},
    403: {"description": "Forbidden — insufficient role or account is inactive."},
    429: {"description": "Rate limit exceeded."},
}


@router.post(
    "/",
    response_model=FinancialRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a financial record",
    description=(
        "Create a new income or expense record owned by the authenticated user.\n\n"
        "**Required fields:**\n"
        "- `amount` — positive decimal value\n"
        "- `type` — `income` or `expense`\n"
        "- `category` — any string label (e.g. `Salary`, `Groceries`)\n"
        "- `date` — ISO-8601 format `YYYY-MM-DD`\n\n"
        "**Optional fields:**\n"
        "- `notes` — free-text description\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **30 requests / minute**."
    ),
    response_description="The newly created financial record including server-assigned `id` and `created_at`.",
    responses={
        201: {"description": "Record created successfully."},
        422: {"description": "Validation error — e.g. negative amount or missing required field."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("30/minute")
async def create_financial_record(
    request: Request,
    record_data: FinancialRecordCreate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Create a new financial record (admin only).

    Args:
        request (Request): slowapi rate-limit key source.
        record_data (FinancialRecordCreate): Validated record payload.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user.

    Returns:
        FinancialRecordRead: The persisted record.
    """
    dal = FinancialRecordDAL(db)
    return await dal.create_record(user_id=user.id, **record_data.model_dump())


@router.get(
    "/",
    response_model=list[FinancialRecordRead],
    summary="List financial records",
    description=(
        "Retrieve a paginated, filtered list of the authenticated user's "
        "active (non-deleted) financial records, ordered by date descending.\n\n"
        "### Filtering\n"
        "All filter parameters are optional and combinable:\n\n"
        "| Parameter | Type | Description |\n"
        "|-----------|------|-------------|\n"
        "| `start_date` | `YYYY-MM-DD` | Include records on or after this date |\n"
        "| `end_date` | `YYYY-MM-DD` | Include records on or before this date |\n"
        "| `category` | `string` | Exact category match |\n"
        "| `type` | `income` \\| `expense` | Filter by record type |\n"
        "| `search` | `string` | Case-insensitive partial match on `category` **or** `notes` |\n\n"
        "### Pagination\n"
        "| Parameter | Default | Description |\n"
        "|-----------|---------|-------------|\n"
        "| `offset` | `0` | Number of records to skip |\n"
        "| `limit` | `100` | Maximum records to return (max 100) |\n\n"
        "> 🔒 Requires **admin** or **analyst** role.\n"
        "> ⚠️ Rate-limited to **100 requests / minute**."
    ),
    response_description="Array of matching financial records. Empty array if none found.",
    responses={
        200: {"description": "Records retrieved successfully."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("100/minute")
async def list_financial_records(
    request: Request,
    start_date: date | None = Query(None, description="Filter records on or after this date (YYYY-MM-DD)."),
    end_date: date | None = Query(None, description="Filter records on or before this date (YYYY-MM-DD)."),
    category: str | None = Query(None, description="Exact category name filter."),
    type: FinancialType | None = Query(None, description="Filter by `income` or `expense`."),
    search: str | None = Query(None, description="Case-insensitive partial match against `category` or `notes`."),
    offset: int = Query(0, ge=0, description="Number of records to skip (pagination)."),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return."),
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst])),
):
    """
    List financial records with optional filtering and pagination.

    Args:
        request (Request): slowapi rate-limit key source.
        start_date: Lower-bound date filter.
        end_date: Upper-bound date filter.
        category: Exact category filter.
        type: Record type filter.
        search: Fuzzy search across category and notes.
        offset: Pagination skip count.
        limit: Pagination page size.
        db (AsyncSession): Database session.
        user (Any): Authenticated user (admin or analyst).

    Returns:
        list[FinancialRecordRead]: Matching records ordered by date DESC.
    """
    dal = FinancialRecordDAL(db)
    return await dal.get_records_by_user(
        user_id=user.id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        type=type,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get dashboard summary",
    description=(
        "Returns an aggregated financial overview for the authenticated user:\n\n"
        "- **`total_income`** — sum of all active income records\n"
        "- **`total_expenses`** — sum of all active expense records\n"
        "- **`net_balance`** — `total_income − total_expenses`\n"
        "- **`category_summaries`** — per-category breakdown of totals\n\n"
        "Soft-deleted records are **excluded** from all figures.\n\n"
        "> 🔒 Requires **admin**, **analyst**, or **viewer** role.\n"
        "> ⚠️ Rate-limited to **60 requests / minute**."
    ),
    response_description="Financial overview with totals and per-category breakdown.",
    responses={
        200: {"description": "Dashboard summary calculated successfully."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("60/minute")
async def get_financial_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst, UserRole.viewer])),
):
    """
    Return aggregated financial totals (all roles).

    Args:
        request (Request): slowapi rate-limit key source.
        db (AsyncSession): Database session.
        user (Any): Authenticated user (any role).

    Returns:
        DashboardSummary: Income, expense, balance, and category breakdown.
    """
    dal = FinancialRecordDAL(db)
    return await dal.get_dashboard_summary(user_id=user.id)


@router.get(
    "/{record_id}",
    response_model=FinancialRecordRead,
    summary="Get a single financial record",
    description=(
        "Fetch one specific financial record by its numeric ID.\n\n"
        "Records are **user-scoped** — a user can only retrieve their own records. "
        "Attempting to access another user's record ID returns `404` (not `403`) "
        "to avoid leaking information about the existence of the record.\n\n"
        "Soft-deleted records are also returned as `404`.\n\n"
        "> 🔒 Requires **admin** or **analyst** role.\n"
        "> ⚠️ Rate-limited to **100 requests / minute**."
    ),
    response_description="The requested financial record.",
    responses={
        200: {"description": "Record found and returned."},
        404: {"description": "Record not found, belongs to another user, or has been soft-deleted."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("100/minute")
async def get_financial_record(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst])),
):
    """
    Retrieve a single financial record by ID (admin or analyst).

    Args:
        request (Request): slowapi rate-limit key source.
        record_id (int): Primary key of the target record.
        db (AsyncSession): Database session.
        user (Any): Authenticated user (admin or analyst).

    Raises:
        HTTPException: 404 if not found, deleted, or owned by another user.

    Returns:
        FinancialRecordRead: The matched record.
    """
    dal = FinancialRecordDAL(db)
    record = await dal.get_record_by_id(record_id, user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.patch(
    "/{record_id}",
    response_model=FinancialRecordRead,
    summary="Update a financial record",
    description=(
        "Partially update an existing financial record. All fields are optional — "
        "only the fields you provide will be changed, leaving the rest untouched.\n\n"
        "**Updatable fields:** `amount`, `type`, `category`, `date`, `notes`.\n\n"
        "Records are user-scoped; you can only update records you own. "
        "Providing an ID for a record belonging to another user returns `404`.\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **30 requests / minute**."
    ),
    response_description="The financial record after applying the requested changes.",
    responses={
        200: {"description": "Record updated successfully."},
        404: {"description": "Record not found or belongs to another user."},
        422: {"description": "Validation error — e.g. negative amount."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("30/minute")
async def update_financial_record(
    request: Request,
    record_id: int,
    record_data: FinancialRecordUpdate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Partially update a financial record (admin only).

    Args:
        request (Request): slowapi rate-limit key source.
        record_id (int): Primary key of the record to update.
        record_data (FinancialRecordUpdate): Fields to change.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user.

    Raises:
        HTTPException: 404 if not found or user does not own the record.

    Returns:
        FinancialRecordRead: The updated record.
    """
    dal = FinancialRecordDAL(db)
    record = await dal.update_record(
        record_id, user.id, **record_data.model_dump(exclude_unset=True)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a financial record",
    description=(
        "Mark a financial record as deleted without physically removing it from "
        "the database (`is_deleted = true`).\n\n"
        "**Effect of soft-deletion:**\n"
        "- Hidden from all `GET /financial-records/` listing responses.\n"
        "- Excluded from `GET /financial-records/summary` totals.\n"
        "- Still accessible to database administrators for audit purposes.\n\n"
        "Attempting to delete a record that is already deleted or belongs to "
        "another user returns `404`.\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **30 requests / minute**."
    ),
    response_description="Empty body — `204 No Content` on success.",
    responses={
        204: {"description": "Record soft-deleted successfully."},
        404: {"description": "Record not found or belongs to another user."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("30/minute")
async def delete_financial_record(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Soft-delete a financial record (admin only).

    Args:
        request (Request): slowapi rate-limit key source.
        record_id (int): Primary key of the record to delete.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user.

    Raises:
        HTTPException: 404 if not found or user does not own the record.
    """
    dal = FinancialRecordDAL(db)
    success = await dal.soft_delete_record(record_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")

"""
Financial records router defining endpoint paths for the core CRUD and summarization behaviors.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import (
    FinancialRecordCreate, 
    FinancialRecordRead,
    FinancialRecordUpdate,
    DashboardSummary,
    UserRole
)
from models import FinancialType
from financial_dal import FinancialRecordDAL
from dependencies import get_db, RoleChecker, limiter
from typing import Any
from datetime import date

router = APIRouter(prefix="/financial-records", tags=["Financial Records"])

@router.post("/", response_model=FinancialRecordRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_financial_record(
    request: Request,
    record_data: FinancialRecordCreate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin]))
):
    """
    Creates a new financial record associated with the authenticated user.

    Args:
        request (Request): Active request context used specifically for rate limits.
        record_data (FinancialRecordCreate): Payload containing amount, type, etc.
        db (AsyncSession): Transient database context matching current scope.
        user (Any): Pre-validated session extracting target ownership.

    Returns:
        FinancialRecordRead: Safely serialized response struct of the new item.
    """
    dal = FinancialRecordDAL(db)
    return await dal.create_record(user_id=user.id, **record_data.model_dump())

@router.get("/", response_model=list[FinancialRecordRead])
@limiter.limit("100/minute")
async def list_financial_records(
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    type: FinancialType | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst, UserRole.viewer]))
):
    """
    Retrieves a paginated list of all active financial records bound to the user.

    Args:
        request (Request): Tracked parameter mapping connection info limits.
        start_date (date | None): Window limit lower bounds.
        end_date (date | None): Window limit upper bounds.
        category (str | None): Distinct category filtering.
        type (FinancialType | None): Distinct string marker.
        search (str | None): General fuzzy string filter searching the notes.
        offset (int): Sequence jump start pointer element.
        limit (int): Top boundary extraction limiter.
        db (AsyncSession): Data link session.
        user (Any): Pre-validated requester config payload.

    Returns:
        list[FinancialRecordRead]: Bounding sequence representation.
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
        limit=limit
    )

@router.get("/summary", response_model=DashboardSummary)
@limiter.limit("60/minute")
async def get_financial_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst]))
):
    """
    Calculates dynamic aggregated totals describing an overarching account state.

    Args:
        request (Request): Standard tracked payload scope identifier.
        db (AsyncSession): The operational database linkage.
        user (Any): Requesting User authorization data blob.

    Returns:
        DashboardSummary: Highly structured aggregated JSON overview format.
    """
    dal = FinancialRecordDAL(db)
    return await dal.get_dashboard_summary(user_id=user.id)

@router.get("/{record_id}", response_model=FinancialRecordRead)
@limiter.limit("100/minute")
async def get_financial_record(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin, UserRole.analyst, UserRole.viewer]))
):
    """
    Fetches one unambiguous item entity based exclusively off its system key.

    Args:
        request (Request): Limiter tracker block context payload.
        record_id (int): Absolute location primary mapping integer locator.
        db (AsyncSession): Execution target session parameter argument.
        user (Any): Confirmed authorization schema instance scope ownership mapping.

    Raises:
        HTTPException: Raises 404 target mismatch exception blocking traversal access cases.

    Returns:
        FinancialRecordRead: Filtered structure exposing non-secret state segments.
    """
    dal = FinancialRecordDAL(db)
    record = await dal.get_record_by_id(record_id, user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record

@router.patch("/{record_id}", response_model=FinancialRecordRead)
@limiter.limit("30/minute")
async def update_financial_record(
    request: Request,
    record_id: int,
    record_data: FinancialRecordUpdate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin]))
):
    """
    Overlays discrete modifications onto pre-existent structured data layers mapping user intent.

    Args:
        request (Request): Tracking wrapper parameters restricting operational bounds effectively isolating blocks.
        record_id (int): Fixed physical routing identifier node reference target node index map path constraint rule anchor scope bound anchor key argument map reference rule key reference locator.
        record_data (FinancialRecordUpdate): Config parameters patching existing attributes logic model mapping configurations structures arguments fields instances objects instances properties.
        db (AsyncSession): Primary execution engine payload context boundary pointer configuration scope tracking identifier element rule object configuration link state tracker logic context layer root source stream context context node mapping engine.
        user (Any): Verified role mapping instance token reference object path payload struct reference object parameter block parameter item structure struct structure constraint pointer map bound reference mapping logic.

    Raises:
        HTTPException: Raises 404.

    Returns:
        FinancialRecordRead: Valid patched read projection mapping entity scope boundaries limits definitions bounds constraints.
    """
    dal = FinancialRecordDAL(db)
    record = await dal.update_record(record_id, user.id, **record_data.model_dump(exclude_unset=True))
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record

@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_financial_record(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin]))
):
    """
    Soft-deletes a record instance hiding it from standard listings and aggregation outputs logic mappings blocks definitions scope blocks mapping limits parameters map configuration rules instance objects tracking context engine.

    Args:
        request (Request): Scope identifier struct limit constraints context stream wrapper limits context bounds identifier token structure rule scope map object link payload map pointer object boundary engine structure layer key logic bounds reference map rule index link engine pointer parameter engine anchor block root bounds rule bounds pointer.
        record_id (int): Primary reference identifier.
        db (AsyncSession): Link mapping database constraint tracking rule payload context context node object structure tracking parameter block instance mapping payload item item logic model parameters layer bounds context rule.
        user (Any): Context identity instance struct mappings.

    Raises:
        HTTPException: Standard not found filter exception block.
    """
    dal = FinancialRecordDAL(db)
    success = await dal.soft_delete_record(record_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")

"""
User management router providing admin-only endpoints for listing users,
updating roles, and toggling active/inactive status.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import UserRead, UserUpdate, UserRole
from user_dal import UserDAL
from dependencies import get_db, RoleChecker, limiter
from typing import Any

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/", response_model=list[UserRead])
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    List every user account in the system.

    Args:
        request (Request): Incoming request for rate-limit tracking.
        db (AsyncSession): Active database session.
        user (Any): The authenticated admin user.

    Returns:
        list[UserRead]: All registered user profiles.
    """
    dal = UserDAL(db)
    return await dal.get_all_users()


@router.get("/{user_id}", response_model=UserRead)
@limiter.limit("60/minute")
async def get_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Retrieve a single user by ID.

    Args:
        request (Request): Incoming request for rate-limit tracking.
        user_id (int): The target user's primary key.
        db (AsyncSession): Active database session.
        user (Any): The authenticated admin user.

    Raises:
        HTTPException: 404 if the user does not exist.

    Returns:
        UserRead: The requested user profile.
    """
    dal = UserDAL(db)
    target = await dal.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return target


@router.patch("/{user_id}", response_model=UserRead)
@limiter.limit("30/minute")
async def update_user(
    request: Request,
    user_id: int,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Update a user's role and/or active status (admin only).

    Args:
        request (Request): Incoming request for rate-limit tracking.
        user_id (int): The target user's primary key.
        update_data (UserUpdate): Fields to patch (role, is_active).
        db (AsyncSession): Active database session.
        user (Any): The authenticated admin user.

    Raises:
        HTTPException: 404 if the user does not exist.
        HTTPException: 400 if an admin tries to deactivate themselves.

    Returns:
        UserRead: The updated user profile.
    """
    if user_id == user.id and update_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    dal = UserDAL(db)
    target = await dal.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if update_data.role is not None:
        target = await dal.update_user_role(user_id, update_data.role)

    if update_data.is_active is not None:
        target = await dal.update_user_status(user_id, update_data.is_active)

    return target

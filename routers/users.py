"""
User management router — admin-only endpoints for listing, inspecting,
and modifying user accounts (role and active/inactive status).

All endpoints require an `admin` role JWT.
Rate limits: GET 60/min · PATCH 30/min.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import UserRead, UserUpdate, UserRole
from user_dal import UserDAL
from dependencies import get_db, RoleChecker, limiter
from typing import Any

router = APIRouter(prefix="/users", tags=["User Management"])

_AUTH_ERRORS = {
    401: {"description": "Missing or invalid Authorization header / expired JWT."},
    403: {
        "description": (
            "Forbidden — the authenticated user does not have the `admin` role, "
            "or the account has been deactivated."
        )
    },
    429: {"description": "Rate limit exceeded."},
}


@router.get(
    "/",
    response_model=list[UserRead],
    summary="List all users",
    description=(
        "Returns a complete list of every registered user in the system, "
        "ordered by account creation (ascending ID).\n\n"
        "**Returned fields per user:**\n"
        "- `id` — unique identifier\n"
        "- `email` — registered email\n"
        "- `role` — `viewer` | `analyst` | `admin`\n"
        "- `is_active` — `true` if the account can log in\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **60 requests / minute**."
    ),
    response_description="Array of user profiles (password hashes are never included).",
    responses={
        200: {
            "description": "User list retrieved successfully.",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "email": "admin@example.com", "role": "admin", "is_active": True},
                        {"id": 2, "email": "alice@example.com", "role": "viewer", "is_active": True},
                    ]
                }
            },
        },
        **_AUTH_ERRORS,
    },
)
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Retrieve all registered users (admin only).

    Args:
        request (Request): slowapi rate-limit key source.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user from RoleChecker.

    Returns:
        list[UserRead]: All user profiles, password hashes excluded.
    """
    dal = UserDAL(db)
    return await dal.get_all_users()


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get a specific user",
    description=(
        "Retrieve full profile details for a single user by their numeric ID.\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **60 requests / minute**."
    ),
    response_description="The requested user's profile.",
    responses={
        200: {
            "description": "User profile retrieved.",
            "content": {
                "application/json": {
                    "example": {"id": 2, "email": "alice@example.com", "role": "analyst", "is_active": True}
                }
            },
        },
        404: {"description": "No user found with the given ID."},
        **_AUTH_ERRORS,
    },
)
@limiter.limit("60/minute")
async def get_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(RoleChecker([UserRole.admin])),
):
    """
    Fetch a single user by primary key (admin only).

    Args:
        request (Request): slowapi rate-limit key source.
        user_id (int): Target user's primary key.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user.

    Raises:
        HTTPException: 404 if the user does not exist.

    Returns:
        UserRead: The matched user profile.
    """
    dal = UserDAL(db)
    target = await dal.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return target


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update a user's role or status",
    description=(
        "Partially update a user account — change their **role**, toggle their "
        "**active status**, or both in a single request.\n\n"
        "### Business Rules\n"
        "- **Role change** — promotes or demotes the user. Takes effect immediately "
        "on future requests (existing JWTs are re-checked against the DB on every call).\n"
        "- **Deactivation** (`is_active: false`) — the user's JWT is rejected on all "
        "protected endpoints until they are reactivated.\n"
        "- **Self-deactivation guard** — an admin cannot deactivate their own account "
        "to prevent accidental lock-out.\n\n"
        "> 🔒 Requires **admin** role.\n"
        "> ⚠️ Rate-limited to **30 requests / minute**."
    ),
    response_description="The updated user profile reflecting the applied changes.",
    responses={
        200: {
            "description": "User updated successfully.",
            "content": {
                "application/json": {
                    "example": {"id": 2, "email": "alice@example.com", "role": "analyst", "is_active": False}
                }
            },
        },
        400: {"description": "Admin attempted to deactivate their own account."},
        404: {"description": "No user found with the given ID."},
        **_AUTH_ERRORS,
    },
)
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
        request (Request): slowapi rate-limit key source.
        user_id (int): Target user's primary key.
        update_data (UserUpdate): Fields to patch.
        db (AsyncSession): Database session.
        user (Any): Authenticated admin user.

    Raises:
        HTTPException: 400 if the admin tries to deactivate themselves.
        HTTPException: 404 if the target user does not exist.

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if update_data.role is not None:
        target = await dal.update_user_role(user_id, update_data.role)
    if update_data.is_active is not None:
        target = await dal.update_user_status(user_id, update_data.is_active)

    return target

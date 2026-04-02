"""
Dependency injection definitions including database provisioning,
role-based access control, and rate-limiting setup.
"""
from fastapi import Depends, HTTPException, Request, status
from async_fastapi_jwt_auth import AuthJWT
from sqlalchemy.ext.asyncio import AsyncSession
from models import UserRole
from user_dal import UserDAL
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


async def get_db(request: Request):
    """
    Dependency generating a scoped async DB session for incoming HTTP operations.

    Args:
        request (Request): The incoming request payload containing app state.

    Yields:
        AsyncSession: The active database connection context block.
    """
    async with request.app.state.SessionLocal() as session:
        yield session


class RoleChecker:
    """
    Dependency class designed to enforce role-based access limits on endpoints.

    Attributes:
        allowed_roles (list[UserRole]): A matrix of authorized access profiles.
    """

    def __init__(self, allowed_roles: list[UserRole]):
        """Initialize the checker with permissive roles."""
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        Authorize: AuthJWT = Depends(),
        db: AsyncSession = Depends(get_db)
    ):
        """
        Execute the role validation workflow by extracting the role
        from the JWT and performing a database check.

        Args:
            Authorize (AuthJWT): Injected async authorization engine.
            db (AsyncSession): Standard DB dependency parameter.

        Raises:
            HTTPException: With 403 status if insufficient permissions.

        Returns:
            User: The mapped authorization profile matching the current
                  endpoint payload.
        """
        await Authorize.jwt_required()
        user_id = int(await Authorize.get_jwt_subject())
        dal = UserDAL(db)
        user = await dal.get_user_by_id(user_id)
        if not user or user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return user

"""
Data Access Layer (DAL) for the User model.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, UserRole
from typing import Sequence


class UserDAL:
    """
    Data Access Layer defining standard CRUD operations for users.

    Attributes:
        db_session (AsyncSession): The SQLAlchemy async session context.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize the UserDAL with an async session."""
        self.db_session = db_session

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        role: UserRole = UserRole.viewer,
    ) -> User:
        """
        Create a new user record in the database.

        Args:
            email (str): The email address for the user.
            hashed_password (str): Securely hashed user password.
            role (UserRole, optional): System role. Defaults to UserRole.viewer.

        Returns:
            User: The newly persisted user instance.
        """
        user = User(email=email, hashed_password=hashed_password, role=role)
        self.db_session.add(user)
        await self.db_session.commit()
        await self.db_session.refresh(user)
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        """
        Retrieve a user by their registered email address.

        Args:
            email (str): The email mapped to the desired user.

        Returns:
            User | None: The found user instance, or None if missing.
        """
        query = select(User).where(User.email == email)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def get_user_by_id(self, user_id: int) -> User | None:
        """
        Retrieve a user by their primary key identifier.

        Args:
            user_id (int): The primary ID of the user.

        Returns:
            User | None: The found user instance, or None if missing.
        """
        query = select(User).where(User.id == user_id)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def get_all_users(self) -> Sequence[User]:
        """
        Retrieve every user in the system.

        Returns:
            Sequence[User]: All registered user accounts.
        """
        query = select(User).order_by(User.id)
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def update_user_role(self, user_id: int, role: UserRole) -> User | None:
        """
        Update the clearance role of a specific user.

        Args:
            user_id (int): ID of the user to be patched.
            role (UserRole): The new role literal.

        Returns:
            User | None: The updated user if successful, otherwise None.
        """
        user = await self.get_user_by_id(user_id)
        if user:
            user.role = role
            await self.db_session.commit()
            await self.db_session.refresh(user)
        return user

    async def update_user_status(
        self, user_id: int, is_active: bool
    ) -> User | None:
        """
        Activate or deactivate a user account.

        Args:
            user_id (int): ID of the target user.
            is_active (bool): True to activate, False to deactivate.

        Returns:
            User | None: The updated user if found, otherwise None.
        """
        user = await self.get_user_by_id(user_id)
        if user:
            user.is_active = is_active
            await self.db_session.commit()
            await self.db_session.refresh(user)
        return user

"""
Data Access Layer (DAL) for the User model.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, UserRole

class UserDAL:
    """
    Data Access Layer defining standard CRUD operations for users.
    
    Attributes:
        db_session (AsyncSession): The SQLAlchemy async session context.
    """
    def __init__(self, db_session: AsyncSession):
        """Initializes the UserDAL with an async session."""
        self.db_session = db_session

    async def create_user(self, email: str, hashed_password: str, role: UserRole = UserRole.viewer) -> User:
        """
        Creates a new user record in the database.

        Args:
            email (str): The logical identifier for the user.
            hashed_password (str): Secure hashing of the user password.
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
        Retrieves a user by their registered email address.

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
        Retrieves a user by their primary key identifier.

        Args:
            user_id (int): The primary ID of the user.

        Returns:
            User | None: The found user instance, or None if missing.
        """
        query = select(User).where(User.id == user_id)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def update_user_role(self, user_id: int, role: UserRole) -> User | None:
        """
        Updates the clearance role of a specific user.

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

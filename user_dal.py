from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, UserRole

class UserDAL:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create_user(self, email: str, hashed_password: str, role: UserRole = UserRole.viewer) -> User:
        user = User(email=email, hashed_password=hashed_password, role=role)
        self.db_session.add(user)
        await self.db_session.commit()
        await self.db_session.refresh(user)
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def get_user_by_id(self, user_id: int) -> User | None:
        query = select(User).where(User.id == user_id)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def update_user_role(self, user_id: int, role: UserRole) -> User | None:
        user = await self.get_user_by_id(user_id)
        if user:
            user.role = role
            await self.db_session.commit()
            await self.db_session.refresh(user)
        return user

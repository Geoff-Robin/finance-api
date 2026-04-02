from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Enum
import enum

Base = declarative_base()

class UserRole(str, enum.Enum):
    viewer = "viewer"
    analyst = "analyst"
    admin = "admin"

class User(Base):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    role = Column(
        Enum(UserRole, name="user_roles"),
        default=UserRole.viewer,
        nullable=False
    )

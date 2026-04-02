"""
This module contains the SQLAlchemy ORM models and enums for the database.
"""
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Enum, ForeignKey, Numeric, Date, Boolean,
    DateTime, Index, func, text,
)
import enum
import datetime

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass

class UserRole(str, enum.Enum):
    """Enumeration of user roles within the system."""
    viewer = "viewer"
    analyst = "analyst"
    admin = "admin"

class FinancialType(str, enum.Enum):
    """Enumeration of financial record types."""
    income = "income"
    expense = "expense"

class User(Base):
    """
    User model representing an account in the system.

    Attributes:
        id (int): Primary key for the user.
        email (str): Unique email address used for login.
        hashed_password (str): The securely hashed user password.
        role (UserRole): The system clearance role of the user.
        is_active (bool): Whether the user account is active or deactivated.
        records (list[FinancialRecord]): The financial records owned by the user.

    Indexes:
        ix_users_email: Unique B-tree index on email (login lookup).
        ix_users_is_active: Partial index on is_active=False (inactive check).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_roles"),
        default=UserRole.viewer,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    records: Mapped[list["FinancialRecord"]] = relationship(back_populates="user")

    __table_args__ = (
        Index(
            "ix_users_is_active_false",
            "is_active",
            postgresql_where=text("is_active = FALSE"),
        ),
    )


class FinancialRecord(Base):
    """
    Financial record model for tracking incomes or expenses.

    Attributes:
        id (int): Primary key for the financial record.
        user_id (int): Foreign key identifier mapping to the owning user.
        amount (float): The total monetary value of the record.
        type (FinancialType): The classification type (income or expense).
        category (str): The user-defined or system-defined category.
        date (datetime.date): The date the transaction occurred.
        notes (str | None): Optional user notes or details.
        is_deleted (bool): If True, marks this record as soft-deleted.
        created_at (datetime.datetime): When the record was first inserted.
        user (User): The back-reference mapped to the User instance.

    Indexes:
        ix_fr_user_deleted:         (user_id, is_deleted) — universal filter.
        ix_fr_user_deleted_date:    (user_id, is_deleted, date DESC) — listing
                                    + date range filters + ORDER BY.
        ix_fr_user_deleted_type:    (user_id, is_deleted, type) — dashboard SUM
                                    aggregations per income/expense type.
        ix_fr_user_deleted_cat:     (user_id, is_deleted, category) — category
                                    filter + GROUP BY in dashboard summary.
    """
    __tablename__ = "financial_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    type: Mapped[FinancialType] = mapped_column(
        Enum(FinancialType, name="financial_types"), nullable=False
    )
    category: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="records")

    __table_args__ = (
        Index("ix_fr_user_deleted", "user_id", "is_deleted"),
        Index("ix_fr_user_deleted_date", "user_id", "is_deleted", "date"),
        Index("ix_fr_user_deleted_type", "user_id", "is_deleted", "type"),
        Index("ix_fr_user_deleted_cat", "user_id", "is_deleted", "category"),
    )

"""
This module defines the Pydantic schemas used for API data validation and serialization.
"""
from pydantic import BaseModel, Field, ConfigDict
from models import UserRole, FinancialType
import datetime as dt
from decimal import Decimal


# ── Authentication ──────────────────────────────────────────────────


class UserCreate(BaseModel):
    """Schema for parsing incoming user registration data."""
    email: str
    password: str
    role: UserRole = UserRole.viewer


class UserLogin(BaseModel):
    """Schema for parsing incoming user login credentials."""
    email: str
    password: str


# ── User Management ────────────────────────────────────────────────


class UserRead(BaseModel):
    """Schema for serialised user responses (no password exposed)."""
    id: int
    email: str
    role: UserRole
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Schema for admin-driven partial user updates (role / status)."""
    role: UserRole | None = None
    is_active: bool | None = None


# ── Financial Records ──────────────────────────────────────────────


class FinancialRecordBase(BaseModel):
    """Base schema holding common fields for financial records."""
    amount: Decimal = Field(..., gt=0)
    type: FinancialType
    category: str
    date: dt.date
    notes: str | None = None


class FinancialRecordCreate(FinancialRecordBase):
    """Schema for validating financial record creation requests."""
    pass


class FinancialRecordUpdate(BaseModel):
    """Schema for validating partial updates to a financial record."""
    amount: Decimal | None = Field(None, gt=0)
    type: FinancialType | None = None
    category: str | None = None
    date: dt.date | None = None
    notes: str | None = None


class FinancialRecordRead(FinancialRecordBase):
    """Schema for serialised financial record API responses."""
    id: int
    user_id: int
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


# ── Dashboard / Summary ───────────────────────────────────────────


class CategorySummary(BaseModel):
    """Schema representing an aggregated sum for a particular category."""
    category: str
    total: Decimal


class DashboardSummary(BaseModel):
    """Schema for the dashboard summary payload detailing overall financial health."""
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    category_summaries: list[CategorySummary]

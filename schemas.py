"""
Pydantic schemas used for API request validation and response serialization.

Every schema carries Field-level descriptions and a ``json_schema_extra``
example block so Swagger UI renders rich, pre-filled request bodies.
"""
from pydantic import BaseModel, Field, ConfigDict
from models import UserRole, FinancialType
import datetime as dt
from decimal import Decimal



class UserCreate(BaseModel):
    """Payload for creating a new user account."""

    email: str = Field(
        ...,
        description="A unique, valid email address for the new account.",
        examples=["alice@example.com"],
    )
    password: str = Field(
        ...,
        min_length=4,
        description="Plaintext password (will be hashed server-side with Argon2).",
        examples=["s3cur3p@ss"],
    )
    role: UserRole = Field(
        UserRole.viewer,
        description=(
            "System role assigned to the account. "
            "One of `viewer`, `analyst`, or `admin`."
        ),
        examples=["viewer"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "alice@example.com",
                "password": "s3cur3p@ss",
                "role": "viewer",
            }
        }
    )


class UserLogin(BaseModel):
    """Credentials used to authenticate an existing user."""

    email: str = Field(
        ...,
        description="Registered email address.",
        examples=["alice@example.com"],
    )
    password: str = Field(
        ...,
        description="Plaintext password for the account.",
        examples=["s3cur3p@ss"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "alice@example.com",
                "password": "s3cur3p@ss",
            }
        }
    )



class UserRead(BaseModel):
    """Public user profile returned by the user-management endpoints."""

    id: int = Field(..., description="Auto-generated primary key.")
    email: str = Field(..., description="Unique email address of the user.")
    role: UserRole = Field(..., description="Current system role of the user.")
    is_active: bool = Field(
        ...,
        description=(
            "Whether the account is active. Deactivated accounts cannot log in "
            "and their existing JWTs are rejected immediately."
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "email": "alice@example.com",
                "role": "analyst",
                "is_active": True,
            }
        },
    )


class UserUpdate(BaseModel):
    """
    Admin-driven partial update for a user account.
    Both fields are optional — supply only those you wish to change.
    """

    role: UserRole | None = Field(
        None,
        description="Promote or demote the user to a different role.",
        examples=["analyst"],
    )
    is_active: bool | None = Field(
        None,
        description=(
            "`true` to reactivate a suspended account; "
            "`false` to deactivate it. "
            "Admins cannot deactivate their own account."
        ),
        examples=[False],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"role": "analyst", "is_active": True}
        }
    )


class FinancialRecordBase(BaseModel):
    """Shared fields for all financial record schemas."""

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Monetary value of the transaction. Must be greater than 0.",
        examples=["1500.00"],
    )
    type: FinancialType = Field(
        ...,
        description="Classification of the record: `income` or `expense`.",
        examples=["income"],
    )
    category: str = Field(
        ...,
        description="User-defined label grouping similar transactions (e.g. 'Salary', 'Rent').",
        examples=["Salary"],
    )
    date: dt.date = Field(
        ...,
        description="ISO-8601 date on which the transaction occurred (`YYYY-MM-DD`).",
        examples=["2024-04-01"],
    )
    notes: str | None = Field(
        None,
        description="Optional free-text notes or description for the record.",
        examples=["March take-home pay after tax."],
    )


class FinancialRecordCreate(FinancialRecordBase):
    """Request body for creating a new financial record (admin only)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "1500.00",
                "type": "income",
                "category": "Salary",
                "date": "2024-04-01",
                "notes": "March take-home pay after tax.",
            }
        }
    )


class FinancialRecordUpdate(BaseModel):
    """
    Request body for partially updating a financial record.
    All fields are optional — only supplied fields will be changed.
    """

    amount: Decimal | None = Field(
        None, gt=0, description="New monetary value. Must be greater than 0.", examples=["1750.00"]
    )
    type: FinancialType | None = Field(
        None, description="Change the record type to `income` or `expense`.", examples=["expense"]
    )
    category: str | None = Field(
        None, description="New category label.", examples=["Freelance"]
    )
    date: dt.date | None = Field(
        None, description="Corrected transaction date.", examples=["2024-04-15"]
    )
    notes: str | None = Field(
        None, description="Updated notes or description.", examples=["Revised amount after bonus."]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "1750.00",
                "notes": "Revised amount after bonus.",
            }
        }
    )


class FinancialRecordRead(FinancialRecordBase):
    """Full financial record as returned by the API (includes server-set fields)."""

    id: int = Field(..., description="Auto-generated primary key of the record.")
    user_id: int = Field(..., description="ID of the user who owns this record.")
    created_at: dt.datetime = Field(
        ..., description="UTC timestamp of when the record was first created."
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "user_id": 2,
                "amount": "1500.00",
                "type": "income",
                "category": "Salary",
                "date": "2024-04-01",
                "notes": "March take-home pay after tax.",
                "created_at": "2024-04-01T09:00:00",
            }
        },
    )





class CategorySummary(BaseModel):
    """Aggregated total for a single spending or income category."""

    category: str = Field(..., description="The category label.")
    total: Decimal = Field(..., description="Sum of all non-deleted record amounts in this category.")

    model_config = ConfigDict(
        json_schema_extra={"example": {"category": "Rent", "total": "1200.00"}}
    )


class DashboardSummary(BaseModel):
    """
    High-level financial overview for the authenticated user.

    Soft-deleted records are excluded from all figures.
    """

    total_income: Decimal = Field(
        ..., description="Sum of all active income records."
    )
    total_expenses: Decimal = Field(
        ..., description="Sum of all active expense records."
    )
    net_balance: Decimal = Field(
        ..., description="``total_income`` minus ``total_expenses``."
    )
    category_summaries: list[CategorySummary] = Field(
        ...,
        description="Per-category breakdown of total amounts across all record types.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_income": "3500.00",
                "total_expenses": "1200.00",
                "net_balance": "2300.00",
                "category_summaries": [
                    {"category": "Salary", "total": "3500.00"},
                    {"category": "Rent", "total": "1200.00"},
                ],
            }
        }
    )

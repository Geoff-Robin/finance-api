"""
Data Access Layer (DAL) for managing financial records and calculating summaries.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, or_
from models import FinancialRecord, FinancialType
from datetime import date
from decimal import Decimal
from typing import Sequence

class FinancialRecordDAL:
    """
    Data Access Layer providing robust operations to interface with
    FinancialRecord models in the database.
    
    Attributes:
        db_session (AsyncSession): The core database interaction phase.
    """
    def __init__(self, db_session: AsyncSession):
        """Initializes the object with an async transactional session."""
        self.db_session = db_session

    async def create_record(self, user_id: int, **kwargs) -> FinancialRecord:
        """
        Creates a new financial record mapping to the user.

        Args:
            user_id (int): ID of the owner.
            **kwargs: Unpacked record parameters matching Pydantic fields.

        Returns:
            FinancialRecord: The newly persisted record.
        """
        record = FinancialRecord(user_id=user_id, **kwargs)
        self.db_session.add(record)
        await self.db_session.commit()
        await self.db_session.refresh(record)
        return record

    async def get_record_by_id(self, record_id: int, user_id: int) -> FinancialRecord | None:
        """
        Locates a single, un-deleted financial record ensuring user ownership.

        Args:
            record_id (int): Primary key.
            user_id (int): The current user's ID for access check.

        Returns:
            FinancialRecord | None: Database instance or None if unavailable/unowned.
        """
        query = select(FinancialRecord).where(
            and_(
                FinancialRecord.id == record_id,
                FinancialRecord.user_id == user_id,
                FinancialRecord.is_deleted == False
            )
        )
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def get_records_by_user(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        category: str | None = None,
        type: FinancialType | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100
    ) -> Sequence[FinancialRecord]:
        """
        Retrieves multiple financial records based on filtering configurations.

        Args:
            user_id (int): Bound user entity identifier.
            start_date (date | None): Optional inclusive bounding early date.
            end_date (date | None): Optional inclusive bounding late date.
            category (str | None): Optional strict category match.
            type (FinancialType | None): Optional record classification standard.
            search (str | None): Optional substring to match against notes or category.
            offset (int): Pagination offset value.
            limit (int): Pagination element cap.

        Returns:
            Sequence[FinancialRecord]: A list or sequence of database models.
        """
        query = select(FinancialRecord).where(
            and_(
                FinancialRecord.user_id == user_id,
                FinancialRecord.is_deleted == False
            )
        )
        
        if start_date:
            query = query.where(FinancialRecord.date >= start_date)
        if end_date:
            query = query.where(FinancialRecord.date <= end_date)
        if category:
            query = query.where(FinancialRecord.category == category)
        if type:
            query = query.where(FinancialRecord.type == type)
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                or_(
                    FinancialRecord.category.ilike(search_filter),
                    FinancialRecord.notes.ilike(search_filter)
                )
            )
            
        query = query.order_by(FinancialRecord.date.desc()).offset(offset).limit(limit)
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def update_record(self, record_id: int, user_id: int, **kwargs) -> FinancialRecord | None:
        """
        Applies a partial update overlay on a specific un-deleted record.

        Args:
            record_id (int): Expected database ID.
            user_id (int): Active user ID to assure modification privileges.
            **kwargs: Field differences.

        Returns:
            FinancialRecord | None: The modified row or None.
        """
        record = await self.get_record_by_id(record_id, user_id)
        if not record:
            return None
            
        for key, value in kwargs.items():
            if value is not None:
                setattr(record, key, value)
        
        await self.db_session.commit()
        await self.db_session.refresh(record)
        return record

    async def soft_delete_record(self, record_id: int, user_id: int) -> bool:
        """
        Marks an item as structurally deleted without actually discarding the data.

        Args:
            record_id (int): Primary key item.
            user_id (int): The current user's ID for access check.

        Returns:
            bool: True if modification occurred, False otherwise.
        """
        record = await self.get_record_by_id(record_id, user_id)
        if not record:
            return False
            
        record.is_deleted = True
        await self.db_session.commit()
        return True

    async def get_dashboard_summary(self, user_id: int) -> dict:
        """
        Generates overarching aggregated stats about the user's financial activity.

        Args:
            user_id (int): Target user configuration.

        Returns:
            dict: Structured aggregation mapping total_income, total_expenses,
                  net_balance, and category_summaries.
        """
        # Total Income
        income_query = select(func.sum(FinancialRecord.amount)).where(
            and_(
                FinancialRecord.user_id == user_id,
                FinancialRecord.type == FinancialType.income,
                FinancialRecord.is_deleted == False
            )
        )
        income_result = await self.db_session.execute(income_query)
        total_income = income_result.scalar() or Decimal("0.00")

        # Total Expenses
        expense_query = select(func.sum(FinancialRecord.amount)).where(
            and_(
                FinancialRecord.user_id == user_id,
                FinancialRecord.type == FinancialType.expense,
                FinancialRecord.is_deleted == False
            )
        )
        expense_result = await self.db_session.execute(expense_query)
        total_expenses = expense_result.scalar() or Decimal("0.00")

        # Category Wise Totals
        category_query = select(
            FinancialRecord.category,
            func.sum(FinancialRecord.amount)
        ).where(
            and_(
                FinancialRecord.user_id == user_id,
                FinancialRecord.is_deleted == False
            )
        ).group_by(FinancialRecord.category)
        
        category_result = await self.db_session.execute(category_query)
        category_summaries = [
            {"category": row[0], "total": row[1]}
            for row in category_result.all()
        ]

        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_balance": total_income - total_expenses,
            "category_summaries": category_summaries
        }

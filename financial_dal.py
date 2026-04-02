from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from models import FinancialRecord, FinancialType
from datetime import date
from decimal import Decimal
from typing import Sequence

class FinancialRecordDAL:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create_record(self, user_id: int, **kwargs) -> FinancialRecord:
        record = FinancialRecord(user_id=user_id, **kwargs)
        self.db_session.add(record)
        await self.db_session.commit()
        await self.db_session.refresh(record)
        return record

    async def get_record_by_id(self, record_id: int, user_id: int) -> FinancialRecord | None:
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
        offset: int = 0,
        limit: int = 100
    ) -> Sequence[FinancialRecord]:
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
            
        query = query.order_by(FinancialRecord.date.desc()).offset(offset).limit(limit)
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def update_record(self, record_id: int, user_id: int, **kwargs) -> FinancialRecord | None:
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
        record = await self.get_record_by_id(record_id, user_id)
        if not record:
            return False
            
        record.is_deleted = True
        await self.db_session.commit()
        return True

    async def get_dashboard_summary(self, user_id: int) -> dict:
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

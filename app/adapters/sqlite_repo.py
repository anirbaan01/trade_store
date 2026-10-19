from typing import Optional, List
from datetime import date
import asyncio
from sqlalchemy import String, Integer, Date, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from app.domain.models import Trade
from app.domain.ports import ITradeRepository

class Base(DeclarativeBase):
    pass

class TradeORM(Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    counter_party_id: Mapped[str] = mapped_column(String(50), nullable=False)
    book_id: Mapped[str] = mapped_column(String(50), nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    expired: Mapped[str] = mapped_column(String(1), nullable=False, default="N")

class SQLiteTradeRepository(ITradeRepository):
    """
    Adapter implementation using SQLAlchemy 2.0 with Python built-in SQLite engine.
    Encapsulates synchronous database calls cleanly via asyncio.to_thread for async callers.
    """
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def _get_by_id_sync(self, trade_id: str) -> Optional[Trade]:
        with self.session_factory() as session:
            orm_obj = session.execute(
                select(TradeORM).where(TradeORM.trade_id == trade_id)
            ).scalar_one_or_none()
            if not orm_obj:
                return None
            return Trade(
                trade_id=orm_obj.trade_id,
                version=orm_obj.version,
                counter_party_id=orm_obj.counter_party_id,
                book_id=orm_obj.book_id,
                maturity_date=orm_obj.maturity_date,
                created_date=orm_obj.created_date or date.today(),
                expired=orm_obj.expired or "N"
            )

    async def get_by_id(self, trade_id: str) -> Optional[Trade]:
        return await asyncio.to_thread(self._get_by_id_sync, trade_id)

    def _save_or_update_sync(self, trade: Trade) -> None:
        c_date = trade.created_date or date.today()
        exp = trade.expired or "N"
        with self.session_factory() as session:
            with session.begin():
                orm_obj = session.execute(
                    select(TradeORM).where(TradeORM.trade_id == trade.trade_id)
                ).scalar_one_or_none()

                if orm_obj:
                    orm_obj.version = trade.version
                    orm_obj.counter_party_id = trade.counter_party_id
                    orm_obj.book_id = trade.book_id
                    orm_obj.maturity_date = trade.maturity_date
                    orm_obj.created_date = c_date
                    orm_obj.expired = exp
                else:
                    new_orm = TradeORM(
                        trade_id=trade.trade_id,
                        version=trade.version,
                        counter_party_id=trade.counter_party_id,
                        book_id=trade.book_id,
                        maturity_date=trade.maturity_date,
                        created_date=c_date,
                        expired=exp
                    )
                    session.add(new_orm)

    async def save_or_update(self, trade: Trade) -> None:
        await asyncio.to_thread(self._save_or_update_sync, trade)

    def _get_all_active_trades_sync(self) -> List[Trade]:
        with self.session_factory() as session:
            orm_list = session.execute(
                select(TradeORM).where(TradeORM.expired == "N")
            ).scalars().all()
            return [
                Trade(
                    trade_id=obj.trade_id,
                    version=obj.version,
                    counter_party_id=obj.counter_party_id,
                    book_id=obj.book_id,
                    maturity_date=obj.maturity_date,
                    created_date=obj.created_date or date.today(),
                    expired=obj.expired or "N"
                )
                for obj in orm_list
            ]

    async def get_all_active_trades(self) -> List[Trade]:
        return await asyncio.to_thread(self._get_all_active_trades_sync)

    def _get_all_trades_sync(self, include_expired: bool) -> List[Trade]:
        with self.session_factory() as session:
            stmt = select(TradeORM)
            if not include_expired:
                stmt = stmt.where(TradeORM.expired == "N")
            orm_list = session.execute(stmt).scalars().all()
            return [
                Trade(
                    trade_id=obj.trade_id,
                    version=obj.version,
                    counter_party_id=obj.counter_party_id,
                    book_id=obj.book_id,
                    maturity_date=obj.maturity_date,
                    created_date=obj.created_date or date.today(),
                    expired=obj.expired or "N"
                )
                for obj in orm_list
            ]

    async def get_all_trades(self, include_expired: bool = True) -> List[Trade]:
        return await asyncio.to_thread(self._get_all_trades_sync, include_expired)

    def _mark_trades_expired_before_sync(self, reference_date: date) -> int:
        with self.session_factory() as session:
            with session.begin():
                stmt = (
                    update(TradeORM)
                    .where(TradeORM.maturity_date < reference_date, TradeORM.expired == "N")
                    .values(expired="Y")
                )
                result = session.execute(stmt)
                return result.rowcount

    async def mark_trades_expired_before(self, reference_date: date) -> int:
        return await asyncio.to_thread(self._mark_trades_expired_before_sync, reference_date)

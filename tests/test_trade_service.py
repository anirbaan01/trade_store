import unittest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.adapters.sqlite_repo import Base, SQLiteTradeRepository
from app.adapters.memory_cache import InMemoryTradeStateCache
from app.domain.models import Trade
from app.domain.exceptions import LowerVersionTradeException, InvalidMaturityDateException
from app.services.trade_service import TradeService

class TestTradeService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)
        self.repo = SQLiteTradeRepository(self.session_factory)
        self.cache = InMemoryTradeStateCache()
        self.trade_service = TradeService(self.repo, self.cache)

    async def asyncTearDown(self):
        self.engine.dispose()

    async def test_successful_new_trade_ingestion(self):
        today = date.today()
        future_date = today + timedelta(days=30)

        trade = Trade("T1", 1, "CP-1", "B1", future_date)
        result = await self.trade_service.process_trade(trade, current_date=today)

        self.assertEqual(result.trade_id, "T1")
        self.assertEqual(result.version, 1)

        stored = await self.repo.get_by_id("T1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.version, 1)
        self.assertEqual(stored.counter_party_id, "CP-1")

    async def test_reject_lower_version_trade(self):
        today = date.today()
        future_date = today + timedelta(days=30)

        t2_v2 = Trade("T2", 2, "CP-2", "B1", future_date)
        await self.trade_service.process_trade(t2_v2, current_date=today)

        t2_v1 = Trade("T2", 1, "CP-1", "B1", future_date)

        with self.assertRaises(LowerVersionTradeException) as cm:
            await self.trade_service.process_trade(t2_v1, current_date=today)

        self.assertEqual(cm.exception.trade_id, "T2")
        self.assertEqual(cm.exception.incoming_version, 1)
        self.assertEqual(cm.exception.existing_version, 2)

    async def test_same_version_replaces_existing_record(self):
        today = date.today()
        future_date = today + timedelta(days=30)

        t1_v1 = Trade("T1", 1, "CP-1", "B1", future_date)
        await self.trade_service.process_trade(t1_v1, current_date=today)

        t1_v1_updated = Trade("T1", 1, "CP-99", "B1", future_date)
        await self.trade_service.process_trade(t1_v1_updated, current_date=today)

        stored = await self.repo.get_by_id("T1")
        self.assertEqual(stored.counter_party_id, "CP-99")

    async def test_higher_version_updates_record(self):
        today = date.today()
        future_date = today + timedelta(days=30)

        t1_v1 = Trade("T1", 1, "CP-1", "B1", future_date)
        await self.trade_service.process_trade(t1_v1, current_date=today)

        t1_v2 = Trade("T1", 2, "CP-1", "B1", future_date)
        await self.trade_service.process_trade(t1_v2, current_date=today)

        stored = await self.repo.get_by_id("T1")
        self.assertEqual(stored.version, 2)

    async def test_reject_trade_with_past_maturity_date(self):
        today = date.today()
        past_date = today - timedelta(days=1)

        t3 = Trade("T3", 1, "CP-3", "B2", past_date)

        with self.assertRaises(InvalidMaturityDateException) as cm:
            await self.trade_service.process_trade(t3, current_date=today)

        self.assertEqual(cm.exception.trade_id, "T3")
        self.assertEqual(cm.exception.maturity_date, past_date)

if __name__ == "__main__":
    unittest.main()

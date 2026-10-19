import unittest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.adapters.sqlite_repo import Base, SQLiteTradeRepository
from app.domain.models import Trade
from app.services.expiration_job import TradeExpirationJob

class TestSQLiteRepoAndExpiration(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)
        self.repo = SQLiteTradeRepository(self.session_factory)
        self.expiration_job = TradeExpirationJob(self.repo)

    async def asyncTearDown(self):
        self.engine.dispose()

    async def test_auto_expiration_job(self):
        today = date.today()
        past_date = today - timedelta(days=5)
        future_date = today + timedelta(days=10)

        matured_trade = Trade("T_MATURED", 1, "CP-1", "B1", past_date, created_date=past_date, expired="N")
        active_trade = Trade("T_ACTIVE", 1, "CP-2", "B1", future_date, created_date=today, expired="N")

        await self.repo.save_or_update(matured_trade)
        await self.repo.save_or_update(active_trade)

        expired_count = await self.expiration_job.execute_expiration_check(current_date=today)
        self.assertEqual(expired_count, 1)

        updated_matured = await self.repo.get_by_id("T_MATURED")
        self.assertEqual(updated_matured.expired, "Y")

        updated_active = await self.repo.get_by_id("T_ACTIVE")
        self.assertEqual(updated_active.expired, "N")

if __name__ == "__main__":
    unittest.main()

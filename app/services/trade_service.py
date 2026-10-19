from datetime import date
from typing import Optional
from app.domain.models import Trade
from app.domain.ports import ITradeRepository, ITradeStateCache
from app.domain.exceptions import LowerVersionTradeException, InvalidMaturityDateException

class TradeService:
    """
    Application Core Use Case: Enforces Trade Ingestion Business Rules.
    """
    def __init__(self, repository: ITradeRepository, cache: ITradeStateCache):
        self.repository = repository
        self.cache = cache

    async def process_trade(self, trade: Trade, current_date: Optional[date] = None) -> Trade:
        """
        Processes and validates an incoming trade transaction.

        Validation Rules:
        1. Reject trade if maturity date < today's date.
        2. Reject trade if version < current existing version for the same Trade ID.
        3. Replace existing record if version == current version.
        4. Insert record if version > current version (or new Trade ID).
        """
        today = current_date or date.today()

        # Validation Rule 1: Maturity Date Check
        if trade.maturity_date < today:
            raise InvalidMaturityDateException(
                trade_id=trade.trade_id,
                maturity_date=trade.maturity_date,
                current_date=today
            )

        # Validation Rule 2: Version Check (using fast cache first, fallback to DB)
        cached_version = await self.cache.get_latest_version(trade.trade_id)
        if cached_version is None:
            existing_trade = await self.repository.get_by_id(trade.trade_id)
            if existing_trade:
                cached_version = existing_trade.version
                await self.cache.set_latest_version(trade.trade_id, cached_version)

        if cached_version is not None:
            if trade.version < cached_version:
                raise LowerVersionTradeException(
                    trade_id=trade.trade_id,
                    incoming_version=trade.version,
                    existing_version=cached_version
                )

        # Save to SQL Store
        await self.repository.save_or_update(trade)

        # Update Fast State Cache
        if cached_version is None or trade.version >= cached_version:
            await self.cache.set_latest_version(trade.trade_id, trade.version)

        return trade

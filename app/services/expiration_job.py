from datetime import date
from typing import Optional
from app.domain.ports import ITradeRepository

class TradeExpirationJob:
    """
    Background worker service that scans active trades and automatically marks
    trades as expired ('Expired = Y') when their maturity date is surpassed.
    """
    def __init__(self, repository: ITradeRepository):
        self.repository = repository

    async def execute_expiration_check(self, current_date: Optional[date] = None) -> int:
        """
        Executes bulk expiration update. Returns the count of trades marked as expired.
        """
        today = current_date or date.today()
        expired_count = await self.repository.mark_trades_expired_before(today)
        return expired_count

from datetime import date
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Trade:
    """
    Core Domain Entity representing a Financial Trade.
    """
    trade_id: str
    version: int
    counter_party_id: str
    book_id: str
    maturity_date: date
    created_date: Optional[date] = None
    expired: str = "N"

    def __post_init__(self):
        if self.created_date is None:
            self.created_date = date.today()
        if not self.expired:
            self.expired = "N"

    def is_expired(self, current_date: Optional[date] = None) -> bool:
        """Check if trade maturity date is strictly prior to given date (defaults to today)."""
        ref_date = current_date or date.today()
        return self.maturity_date < ref_date

    def mark_expired(self) -> None:
        """Domain state mutation: mark trade as expired."""
        self.expired = "Y"

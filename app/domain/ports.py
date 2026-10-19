from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import date
from app.domain.models import Trade

class ITradeRepository(ABC):
    """Port interface for SQL trade persistence store."""

    @abstractmethod
    async def get_by_id(self, trade_id: str) -> Optional[Trade]:
        """Retrieve current stored trade record by Trade ID."""
        pass

    @abstractmethod
    async def save_or_update(self, trade: Trade) -> None:
        """Persist new trade or overwrite existing record if same/higher version."""
        pass

    @abstractmethod
    async def get_all_active_trades(self) -> List[Trade]:
        """Fetch all trades where expired == 'N'."""
        pass

    @abstractmethod
    async def get_all_trades(self, include_expired: bool = True) -> List[Trade]:
        """Fetch all trades stored in the database."""
        pass

    @abstractmethod
    async def mark_trades_expired_before(self, reference_date: date) -> int:
        """Bulk update active trades whose maturity_date < reference_date to expired='Y'. Returns count."""
        pass


class ITradeStateCache(ABC):
    """Port interface for NoSQL / In-memory fast key-value version state lookup."""

    @abstractmethod
    async def get_latest_version(self, trade_id: str) -> Optional[int]:
        """Get latest stored version number for a trade ID."""
        pass

    @abstractmethod
    async def set_latest_version(self, trade_id: str, version: int) -> None:
        """Set or update stored version number for a trade ID."""
        pass


class IEventQueue(ABC):
    """Port interface for streaming queue ingestion."""

    @abstractmethod
    async def publish(self, trade: Trade) -> None:
        """Publish trade event to in-memory streaming queue."""
        pass

    @abstractmethod
    async def consume(self) -> Trade:
        """Consume next trade event from queue."""
        pass

    @abstractmethod
    async def get_queued_trades(self) -> List[Trade]:
        """Get snapshot list of trades currently in queue."""
        pass

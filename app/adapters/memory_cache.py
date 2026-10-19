from typing import Optional, Dict
import asyncio
from app.domain.ports import ITradeStateCache

class InMemoryTradeStateCache(ITradeStateCache):
    """
    Adapter implementation of NoSQL / In-memory fast state store for trade versions.
    Satisfies fast O(1) version validation checks before hitting relational store.
    """
    def __init__(self):
        self._store: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def get_latest_version(self, trade_id: str) -> Optional[int]:
        async with self._lock:
            return self._store.get(trade_id)

    async def set_latest_version(self, trade_id: str, version: int) -> None:
        async with self._lock:
            self._store[trade_id] = version

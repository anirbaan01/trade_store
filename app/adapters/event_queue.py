import asyncio
from typing import List, Optional, Dict, Any
from app.domain.models import Trade
from app.domain.ports import IEventQueue

class InMemoryEventQueue(IEventQueue):
    """
    Adapter implementing an in-memory streaming queue using asyncio.Queue.
    Simulates high-volume real-time trade event transmission with consumer speed & pause controls.
    """
    def __init__(self, maxsize: int = 10000, delay_seconds: float = 0.5, is_paused: bool = False):
        self._queue: asyncio.Queue[Trade] = asyncio.Queue(maxsize=maxsize)
        self.delay_seconds: float = delay_seconds
        self.is_paused: bool = is_paused

    async def publish(self, trade: Trade) -> None:
        await self._queue.put(trade)

    async def consume(self) -> Trade:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    async def get_queued_trades(self) -> List[Trade]:
        """Return snapshot list of trades currently waiting in the queue."""
        return list(self._queue._queue)

    def set_config(self, delay_seconds: Optional[float] = None, is_paused: Optional[bool] = None) -> Dict[str, Any]:
        if delay_seconds is not None:
            self.delay_seconds = max(0.0, float(delay_seconds))
        if is_paused is not None:
            self.is_paused = bool(is_paused)
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        return {
            "delay_seconds": self.delay_seconds,
            "is_paused": self.is_paused,
            "queue_size": self.qsize
        }

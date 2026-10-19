import asyncio
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class ExceptionLogger:
    """
    Audit log for recording trade rejections and domain exceptions.
    Maintains an in-memory buffer with optional persistent file backing (useful for PVC mounts).
    """
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file or os.getenv("EXCEPTION_LOG_PATH")
        self._records: List[Dict[str, Any]] = []
        self._counter = 0
        self._lock = asyncio.Lock()

        if self.log_file and os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r") as f:
                    self._records = json.load(f)
                    self._counter = len(self._records)
            except Exception as e:
                print(f"[ExceptionLogger] Could not load initial exception log from {self.log_file}: {e}")

    async def log_exception(self, trade_id: str, error_type: str, message: str, payload: dict = None) -> Dict[str, Any]:
        async with self._lock:
            self._counter += 1
            record = {
                "id": self._counter,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "trade_id": trade_id,
                "error_type": error_type,
                "message": message,
                "payload": payload or {}
            }
            self._records.append(record)

            if self.log_file:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(self.log_file)), exist_ok=True)
                    with open(self.log_file, "w") as f:
                        json.dump(self._records, f, indent=2)
                except Exception as e:
                    print(f"[ExceptionLogger] Could not persist log to {self.log_file}: {e}")

            return record

    async def get_all_exceptions(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return list(reversed(self._records))

    async def clear(self) -> None:
        async with self._lock:
            self._records.clear()
            self._counter = 0
            if self.log_file and os.path.exists(self.log_file):
                try:
                    os.remove(self.log_file)
                except Exception:
                    pass

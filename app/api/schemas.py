from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List, Dict, Any

class TradeRequest(BaseModel):
    trade_id: str = Field(..., alias="trade_id", description="Unique identifier for the trade", example="T1")
    version: int = Field(..., description="Trade version number", example=1)
    counter_party_id: str = Field(..., alias="counter_party_id", description="Counterparty identifier", example="CP-1")
    book_id: str = Field(..., alias="book_id", description="Book identifier", example="B1")
    maturity_date: date = Field(..., alias="maturity_date", description="Maturity date of trade (YYYY-MM-DD)", example="2026-12-31")

    class Config:
        populate_by_name = True

class TradeResponse(BaseModel):
    trade_id: str
    version: int
    counter_party_id: str
    book_id: str
    maturity_date: date
    created_date: date
    expired: str

    class Config:
        from_attributes = True

class ExceptionResponse(BaseModel):
    error: str
    message: str
    trade_id: str

class ExceptionRecordResponse(BaseModel):
    id: int
    timestamp: str
    trade_id: str
    error_type: str
    message: str
    payload: Dict[str, Any] = {}

class QueueConfigRequest(BaseModel):
    delay_seconds: Optional[float] = Field(None, ge=0.0, description="Consumer processing delay in seconds")
    is_paused: Optional[bool] = Field(None, description="Pause or resume consumer processing")

class QueueConfigResponse(BaseModel):
    delay_seconds: float
    is_paused: bool
    queue_size: int

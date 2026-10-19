from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Dict, Any
from datetime import date
import os
import logging

from app.api.schemas import (
    TradeRequest,
    TradeResponse,
    ExceptionRecordResponse,
    QueueConfigRequest,
    QueueConfigResponse
)
from app.domain.models import Trade
from app.domain.exceptions import LowerVersionTradeException, InvalidMaturityDateException, TradeDomainException
from app.services.trade_service import TradeService
from app.services.expiration_job import TradeExpirationJob
from app.adapters.event_queue import InMemoryEventQueue
from app.adapters.exception_logger import ExceptionLogger

logger = logging.getLogger("trade_store")

router = APIRouter(prefix="/api/v1/trades", tags=["Trades"])

_trade_service: TradeService = None
_expiration_job: TradeExpirationJob = None
_event_queue: InMemoryEventQueue = None
_exception_logger: ExceptionLogger = None
_app_log_path: str = None

def set_dependencies(
    service: TradeService,
    job: TradeExpirationJob,
    queue: InMemoryEventQueue,
    exception_log_adapter: ExceptionLogger,
    log_file_path: str = None
):
    global _trade_service, _expiration_job, _event_queue, _exception_logger, _app_log_path
    _trade_service = service
    _expiration_job = job
    _event_queue = queue
    _exception_logger = exception_log_adapter
    _app_log_path = log_file_path

@router.post("", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def submit_trade(request: TradeRequest):
    """
    Ingest a new trade synchronously and process business validation rules.
    """
    if not _trade_service:
        raise HTTPException(status_code=503, detail="Trade service not initialized")
    trade = Trade(
        trade_id=request.trade_id,
        version=request.version,
        counter_party_id=request.counter_party_id,
        book_id=request.book_id,
        maturity_date=request.maturity_date
    )
    try:
        processed_trade = await _trade_service.process_trade(trade)
        logger.info(f"[Sync Ingest] Successfully processed trade '{trade.trade_id}' v{trade.version}")
        return TradeResponse(
            trade_id=processed_trade.trade_id,
            version=processed_trade.version,
            counter_party_id=processed_trade.counter_party_id,
            book_id=processed_trade.book_id,
            maturity_date=processed_trade.maturity_date,
            created_date=processed_trade.created_date or date.today(),
            expired=processed_trade.expired or "N"
        )
    except LowerVersionTradeException as e:
        logger.warning(f"[Sync Ingest Rejected] {e}")
        if _exception_logger:
            await _exception_logger.log_exception(
                trade_id=e.trade_id,
                error_type="LowerVersionTradeException",
                message=str(e),
                payload=request.model_dump(mode="json")
            )
        raise HTTPException(
            status_code=422,
            detail={"error": "LowerVersionRejected", "message": str(e), "trade_id": e.trade_id}
        )
    except InvalidMaturityDateException as e:
        logger.warning(f"[Sync Ingest Rejected] {e}")
        if _exception_logger:
            await _exception_logger.log_exception(
                trade_id=e.trade_id,
                error_type="InvalidMaturityDateException",
                message=str(e),
                payload=request.model_dump(mode="json")
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "InvalidMaturityDate", "message": str(e), "trade_id": e.trade_id}
        )
    except TradeDomainException as e:
        logger.warning(f"[Sync Ingest Rejected] Domain Exception: {e}")
        if _exception_logger:
            await _exception_logger.log_exception(
                trade_id=getattr(e, "trade_id", request.trade_id),
                error_type=e.__class__.__name__,
                message=str(e),
                payload=request.model_dump(mode="json")
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "DomainException", "message": str(e)}
        )

@router.post("/stream", status_code=status.HTTP_202_ACCEPTED)
async def stream_trade(request: TradeRequest):
    """
    Publish trade transaction to the streaming queue for asynchronous processing.
    """
    if not _event_queue:
        raise HTTPException(status_code=503, detail="Streaming queue not initialized")
    trade = Trade(
        trade_id=request.trade_id,
        version=request.version,
        counter_party_id=request.counter_party_id,
        book_id=request.book_id,
        maturity_date=request.maturity_date
    )
    await _event_queue.publish(trade)
    logger.info(f"[Stream Queue] Queued trade '{trade.trade_id}' v{trade.version}")
    return {"status": "queued", "trade_id": trade.trade_id, "queue_size": _event_queue.qsize}

@router.post("/stream/batch", status_code=status.HTTP_202_ACCEPTED)
async def stream_trade_batch(requests: List[TradeRequest]):
    """
    Publish a batch of trade transactions to the streaming queue for asynchronous processing.
    """
    if not _event_queue:
        raise HTTPException(status_code=503, detail="Streaming queue not initialized")
    queued_ids = []
    for req in requests:
        trade = Trade(
            trade_id=req.trade_id,
            version=req.version,
            counter_party_id=req.counter_party_id,
            book_id=req.book_id,
            maturity_date=req.maturity_date
        )
        await _event_queue.publish(trade)
        queued_ids.append(trade.trade_id)
    logger.info(f"[Stream Queue Batch] Queued batch of {len(queued_ids)} trades")
    return {"status": "queued", "count": len(queued_ids), "trade_ids": queued_ids, "queue_size": _event_queue.qsize}

@router.get("", response_model=List[TradeResponse])
async def list_trades(include_expired: bool = Query(True, description="Whether to include expired trades in the list")):
    """
    Fetch all stored trades from SQLite database.
    """
    if not _trade_service or not _trade_service.repository:
        return []
    trades = await _trade_service.repository.get_all_trades(include_expired=include_expired)
    return [
        TradeResponse(
            trade_id=t.trade_id,
            version=t.version,
            counter_party_id=t.counter_party_id,
            book_id=t.book_id,
            maturity_date=t.maturity_date,
            created_date=t.created_date or date.today(),
            expired=t.expired or "N"
        )
        for t in trades
    ]

@router.get("/queue", response_model=List[TradeResponse])
async def list_queued_trades():
    """
    Fetch snapshot of trades currently waiting in the streaming event queue.
    """
    if not _event_queue:
        return []
    queued_trades = await _event_queue.get_queued_trades()
    return [
        TradeResponse(
            trade_id=t.trade_id,
            version=t.version,
            counter_party_id=t.counter_party_id,
            book_id=t.book_id,
            maturity_date=t.maturity_date,
            created_date=getattr(t, "created_date", None) or date.today(),
            expired=getattr(t, "expired", "N") or "N"
        )
        for t in queued_trades
    ]

@router.get("/queue/config", response_model=QueueConfigResponse)
async def get_queue_config():
    """
    Get current queue consumer configuration (delay_seconds, is_paused, queue_size).
    """
    if not _event_queue:
        return QueueConfigResponse(delay_seconds=0.0, is_paused=False, queue_size=0)
    return _event_queue.get_config()

@router.post("/queue/config", response_model=QueueConfigResponse)
async def update_queue_config(config: QueueConfigRequest):
    """
    Update queue consumer processing delay or pause/resume state.
    """
    if not _event_queue:
        raise HTTPException(status_code=503, detail="Streaming queue not initialized")
    res = _event_queue.set_config(
        delay_seconds=config.delay_seconds,
        is_paused=config.is_paused
    )
    logger.info(f"[Queue Config Updated] paused={res['is_paused']}, delay={res['delay_seconds']}s")
    return res

@router.get("/exceptions", response_model=List[ExceptionRecordResponse])
async def list_exceptions():
    """
    Fetch log of all captured domain exceptions and trade rejections.
    """
    if not _exception_logger:
        return []
    return await _exception_logger.get_all_exceptions()

@router.delete("/exceptions")
async def clear_exceptions():
    """
    Clear all recorded exceptions from the audit log.
    """
    if _exception_logger:
        await _exception_logger.clear()
        logger.info("[Exception Logger] Cleared audit log")
    return {"status": "cleared"}

# -------------------------------------------------------------------
# Documentation & Architecture File Viewing Endpoints for Frontend UI
# -------------------------------------------------------------------

def _get_project_file_content(filename: str) -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    file_path = os.path.join(base_dir, filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file '{filename}': {e}"
    return f"File '{filename}' not found."

@router.get("/docs/readme")
async def get_readme_doc():
    """Returns README.md markdown content for in-UI display."""
    content = _get_project_file_content("README.md")
    return {"filename": "README.md", "content": content}

@router.get("/docs/ai-prompts")
async def get_ai_prompts_doc():
    """Returns AI_PROMPTS.md markdown content for in-UI display."""
    content = _get_project_file_content("AI_PROMPTS.md")
    return {"filename": "AI_PROMPTS.md", "content": content}

@router.get("/docs/diagrams")
async def get_plantuml_diagrams():
    """Returns all PlantUML (.puml) architecture diagrams for in-UI display."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "diagrams"))
    diagrams = []
    if os.path.exists(base_dir):
        for fname in sorted(os.listdir(base_dir)):
            if fname.endswith(".puml"):
                fpath = os.path.join(base_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        diagrams.append({"name": fname.replace(".puml", ""), "filename": fname, "content": f.read()})
                except Exception as e:
                    diagrams.append({"name": fname, "filename": fname, "content": f"Error: {e}"})
    return diagrams

@router.get("/docs/app-log")
async def get_app_log(lines: int = Query(100, ge=1, le=500)):
    """
    Returns recent log lines from the PVC application log file (/data/app.log).
    """
    if not _app_log_path or not os.path.exists(_app_log_path):
        return {"log_path": _app_log_path or "Not configured", "exists": False, "lines": ["Log file not created yet."]}
    
    try:
        with open(_app_log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {
                "log_path": _app_log_path,
                "exists": True,
                "total_lines": len(all_lines),
                "returned_lines": len(recent),
                "content": "".join(recent)
            }
    except Exception as e:
        return {"log_path": _app_log_path, "exists": True, "error": str(e), "content": f"Error reading log file: {e}"}

@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str):
    """
    Fetch a single trade by ID.
    """
    if not _trade_service or not _trade_service.repository:
        raise HTTPException(status_code=503, detail="Trade service not initialized")
    trade = await _trade_service.repository.get_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade '{trade_id}' not found in database")
    return TradeResponse(
        trade_id=trade.trade_id,
        version=trade.version,
        counter_party_id=trade.counter_party_id,
        book_id=trade.book_id,
        maturity_date=trade.maturity_date,
        created_date=trade.created_date or date.today(),
        expired=trade.expired or "N"
    )

@router.post("/trigger-expiration")
async def trigger_expiration():
    """
    Manually execute auto-expiration check against maturity dates.
    """
    if not _expiration_job:
        raise HTTPException(status_code=503, detail="Expiration job not initialized")
    count = await _expiration_job.execute_expiration_check()
    logger.info(f"[Manual Expiration Trigger] Expired {count} trade(s)")
    return {"status": "success", "expired_count": count}

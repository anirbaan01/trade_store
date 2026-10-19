import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.adapters.sqlite_repo import Base, SQLiteTradeRepository
from app.adapters.memory_cache import InMemoryTradeStateCache
from app.adapters.event_queue import InMemoryEventQueue
from app.adapters.exception_logger import ExceptionLogger
from app.services.trade_service import TradeService
from app.services.expiration_job import TradeExpirationJob
from app.api.routes import router, set_dependencies
from app.domain.exceptions import TradeDomainException

# Configure File & Console Logging
raw_log_path = os.getenv("LOG_PATH", os.getenv("APP_LOG_PATH", "/data/app.log" if os.path.exists("/data") else "app.log"))
abs_log_path = os.path.abspath(raw_log_path)
log_dir = os.path.dirname(abs_log_path)
if log_dir:
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"[Warning] Failed to create log directory '{log_dir}': {e}")

logging_handlers = [logging.StreamHandler()]
try:
    file_hnd = logging.FileHandler(abs_log_path, encoding="utf-8")
    file_hnd.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
    logging_handlers.append(file_hnd)
except Exception as e:
    print(f"[Warning] Could not initialize file logging at '{abs_log_path}': {e}")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    handlers=logging_handlers
)
logger = logging.getLogger("trade_store")
logger.info(f"Initialized application logging. Target file: {abs_log_path}")

def create_db_engine(raw_path: str):
    """
    Parses database path, creates parent directories if needed, and initializes
    the SQLAlchemy engine. Falls back gracefully if directory or permission issues occur.
    """
    if ":memory:" in raw_path:
        db_url = "sqlite:///:memory:"
        eng = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False
        )
        return eng, db_url

    if raw_path.startswith("sqlite://"):
        clean_path = raw_path.replace("sqlite:///", "").replace("sqlite://", "")
        abs_path = os.path.abspath(clean_path)
    else:
        abs_path = os.path.abspath(raw_path)

    db_dir = os.path.dirname(abs_path)
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create database directory '{db_dir}': {e}")

    db_url = f"sqlite:///{abs_path}"

    try:
        eng = create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)
        Base.metadata.create_all(bind=eng)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Successfully initialized SQLite database engine at {db_url}")
        return eng, db_url
    except Exception as e:
        logger.warning(f"Database initialization failed for '{db_url}': {e}")
        fallback_path = os.path.abspath("/tmp/trade_store_fallback.db")
        fallback_dir = os.path.dirname(fallback_path)
        if fallback_dir:
            try:
                os.makedirs(fallback_dir, exist_ok=True)
            except Exception:
                pass
        fallback_url = f"sqlite:///{fallback_path}"
        logger.info(f"Falling back to SQLite storage at: {fallback_url}")
        eng = create_engine(fallback_url, connect_args={"check_same_thread": False}, echo=False)
        Base.metadata.create_all(bind=eng)
        return eng, fallback_url

# Configure database connection
raw_db_config = os.getenv("DB_PATH", os.getenv("DATABASE_URL", "sqlite:///:memory:"))
engine, DATABASE_URL = create_db_engine(raw_db_config)
sync_session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

# Instantiate Domain Repositories & Adapters
repo = SQLiteTradeRepository(sync_session_factory)
cache = InMemoryTradeStateCache()
queue = InMemoryEventQueue(delay_seconds=0.5, is_paused=False)

default_log_file = os.getenv("EXCEPTION_LOG_PATH", "/data/exceptions.json" if os.path.exists("/data") else "exceptions.json")
exception_logger = ExceptionLogger(log_file=default_log_file)

# Instantiate Application Use Cases
trade_service = TradeService(repo, cache)
expiration_job = TradeExpirationJob(repo)

# Background Queue Consumer Worker
async def start_queue_consumer(
    queue: InMemoryEventQueue,
    service: TradeService,
    logger_adapter: ExceptionLogger
):
    while True:
        try:
            if queue.is_paused:
                await asyncio.sleep(0.3)
                continue

            if queue.qsize == 0:
                await asyncio.sleep(0.2)
                continue

            if queue.delay_seconds > 0:
                await asyncio.sleep(queue.delay_seconds)

            trade = await queue.consume()
            try:
                await service.process_trade(trade)
                logger.info(f"[Streaming Consumer] Successfully processed trade '{trade.trade_id}' v{trade.version}")
            except TradeDomainException as e:
                logger.warning(f"[Streaming Consumer] Trade Rejected: {e}")
                await logger_adapter.log_exception(
                    trade_id=getattr(e, "trade_id", trade.trade_id),
                    error_type=e.__class__.__name__,
                    message=str(e),
                    payload={
                        "trade_id": trade.trade_id,
                        "version": trade.version,
                        "counter_party_id": trade.counter_party_id,
                        "book_id": trade.book_id,
                        "maturity_date": trade.maturity_date.isoformat(),
                        "mode": "streaming"
                    }
                )
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Streaming Consumer] Unexpected failure: {e}")

# Background Auto-Expiration Scheduler Task
async def start_expiration_scheduler(job: TradeExpirationJob, interval_seconds: int = 60):
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            expired_count = await job.execute_expiration_check()
            if expired_count > 0:
                logger.info(f"[Auto-Expiration Job] Automatically expired {expired_count} trade(s).")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Auto-Expiration Job] Failure: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup phase: Ensure database schema exists
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"DDL verification during lifespan startup: {e}")

    set_dependencies(trade_service, expiration_job, queue, exception_logger, abs_log_path)

    consumer_task = asyncio.create_task(start_queue_consumer(queue, trade_service, exception_logger))
    expiration_task = asyncio.create_task(start_expiration_scheduler(expiration_job, interval_seconds=60))

    yield

    consumer_task.cancel()
    expiration_task.cancel()
    engine.dispose()

app = FastAPI(
    title="Trade Store Application",
    description="Single-container trade ingestion engine with SQLite storage, PVC persistence, and async event streaming.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files directory if present
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Trade Store API is running. Access /docs for Swagger UI."}

app.include_router(router)

@app.get("/health")
async def health_check():
    all_trades = await repo.get_all_trades(include_expired=True) if repo else []
    all_exceptions = await exception_logger.get_all_exceptions() if exception_logger else []
    log_size = os.path.getsize(abs_log_path) if os.path.exists(abs_log_path) else 0
    pvc_active = os.path.exists("/data") and os.access("/data", os.W_OK)
    return {
        "status": "HEALTHY",
        "engine": "SQLite",
        "db_path": DATABASE_URL,
        "log_path": abs_log_path,
        "log_size_bytes": log_size,
        "pvc_mounted": pvc_active,
        "queue_size": queue.qsize if queue else 0,
        "database_trades_count": len(all_trades),
        "exception_count": len(all_exceptions),
        "consumer_paused": queue.is_paused if queue else False,
        "consumer_delay_seconds": queue.delay_seconds if queue else 0.0
    }

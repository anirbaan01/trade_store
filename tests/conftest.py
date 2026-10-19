import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.adapters.sqlite_repo import Base, SQLiteTradeRepository
from app.adapters.memory_cache import InMemoryTradeStateCache
from app.adapters.event_queue import InMemoryEventQueue
from app.services.trade_service import TradeService
from app.services.expiration_job import TradeExpirationJob

@pytest.fixture
def sync_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    yield factory
    engine.dispose()

@pytest.fixture
def repo(sync_session_factory):
    return SQLiteTradeRepository(sync_session_factory)

@pytest.fixture
def cache():
    return InMemoryTradeStateCache()

@pytest.fixture
def queue():
    return InMemoryEventQueue()

@pytest.fixture
def trade_service(repo, cache):
    return TradeService(repo, cache)

@pytest.fixture
def expiration_job(repo):
    return TradeExpirationJob(repo)

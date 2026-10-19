# Trade Store Application

A lightweight, single-container trade processing service built in Python 3.12 using Domain-Driven Design (DDD) and Hexagonal Architecture (Ports & Adapters).

The application ingests financial trades, enforces versioning and maturity validation rules, supports asynchronous streaming ingestion, maintains an embedded SQLite database with an in-memory state cache, logs rejections and application logs to persistent storage, and automatically expires mature trades.

---

## System Architecture

The project follows Hexagonal Architecture to decouple core business logic from infrastructure adapters:

```
                      +------------------------------------------+
                      |     FastAPI REST API / Stream / Web UI    |
                      +--------------------+---------------------+
                                           |
                                           v
+------------------------------------------+------------------------------------------+
|                            CORE APPLICATION SERVICE                                 |
|                                                                                     |
|   [Maturity Date Check] -> [Version Check] -> [Persist / Overwrite] -> [Cache Sync] |
+-------------------+----------------------+------------------------------------------+
                    |                      |
                    v                      v
+-------------------+--------------+   +---+------------------------------------------+
| SQL Persistence Adapter          |   | In-Memory NoSQL State Cache                  |
| (SQLite + SQLAlchemy 2.0)        |   | (O(1) Version Lookup)                        |
+----------------------------------+   +----------------------------------------------+
                    |                      |
                    v                      v
+-------------------+--------------+   +---+------------------------------------------+
| Streaming Queue Adapter          |   | Exception Audit & App File Logger            |
| (asyncio.Queue)                  |   | (Stored in PVC: /data/app.log)               |
+----------------------------------+   +----------------------------------------------+
```

### Key Components
* Core Domain (`app/domain/`): Pure Python entities, custom domain exceptions, and abstract port interfaces (`ITradeRepository`, `ITradeStateCache`, `IEventQueue`).
* Application Services (`app/services/`): `TradeService` enforcing versioning and maturity rules; `TradeExpirationJob` managing background auto-expiration checks.
* Infrastructure Adapters (`app/adapters/`):
  * SQLite repository with SQLAlchemy 2.0 (`sqlite_repo.py`).
  * In-memory key-value state store for fast version checks (`memory_cache.py`).
  * In-process streaming queue (`event_queue.py`).
  * Exception audit logger and application file logger (`exception_logger.py`).
* API & Controller (`app/api/` & `app/main.py`): FastAPI REST controllers, OpenAPI documentation, and interactive web dashboard (`static/index.html`).

---

## Business Rules

| Rule | Condition | Action / Exception |
| :--- | :--- | :--- |
| Maturity Validation | maturity_date < today | Trade rejected immediately (InvalidMaturityDateException, HTTP 400). |
| Lower Version Rule | incoming.version < stored_version | Trade rejected (LowerVersionTradeException, HTTP 422). |
| Same Version Rule | incoming.version == stored_version | Current record in database is overwritten/updated. |
| Higher Version Rule | incoming.version > stored_version | New active trade inserted and state cache updated. |
| Auto-Expiration | maturity_date < today | Background job sets expired = 'Y' for matured trades. |

---

## How to Call the Health Endpoint

The health endpoint provides live system status, SQLite database connection info, queue size, database trade count, exception count, and PVC volume mount status.

* Call via cURL:
  ```bash
  curl -X GET http://localhost:8000/health
  ```
* Sample HTTP Response (200 OK):
  ```json
  {
    "status": "HEALTHY",
    "engine": "SQLite",
    "db_path": "sqlite:////data/trade_store.db",
    "log_path": "/data/app.log",
    "queue_size": 0,
    "database_trades_count": 5,
    "exception_count": 2,
    "pvc_mounted": true,
    "consumer_paused": false,
    "consumer_delay_seconds": 0.5
  }
  ```

---

## How to Run Locally

### 1. Set Up Python Environment
```bash
# Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --no-cache-dir -r requirements.txt
```

### 2. Run Test Suite
```bash
PYTHONPATH=. python -m unittest discover -s tests
```

### 3. Start Application
```bash
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/ in your browser to access the interactive control panel dashboard.

---

## How to Run in Docker

### Option 1: Docker Compose (Recommended)
Build and launch the container with persistent volume storage in detached mode:
```bash
docker compose up -d
```
To view live logs:
```bash
docker compose logs -f
```
To stop the service:
```bash
docker compose down
```

### Option 2: Docker CLI
Build the Docker image:
```bash
docker build -t trade-store:latest .
```
Run the container:
```bash
docker run -d -p 8000:8000 --name trade-store-app trade-store:latest
```

---

## CI/CD Pipeline Notice

Note: The GitHub Actions CI/CD workflow defined in `.github/workflows/ci.yml` is included as a reference configuration and is currently not tested.

---

## Documentation and PlantUML Diagrams in Web UI

The Web Control Panel at http://localhost:8000/ includes a built-in Documentation and Diagram Viewer:
* README.md: Displays project setup and operational documentation.
* AI_PROMPTS.md: Displays the prompt engineering log and review history.
* PlantUML Diagrams: Displays sources for architecture.puml, domain_class.puml, and trade_flow.puml.
* Live App Log: Displays recent lines from /data/app.log.

---

## AI Collaboration Documentation

For details on the prompt engineering workflow and AI generation history, see AI_PROMPTS.md.

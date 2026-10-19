# AI Prompts and Architectural Review Log

This document logs the multi-step prompt workflow used to design, build, and review the Trade Store Application. The development process followed a human-driven, AI-assisted pattern: the engineer provided the requirements, business logic specifications, test matrix, and architectural design, while AI was used to generate initial code skeletons, boilerplate stubs, static code reviews, and the entire single-page frontend control panel (static/index.html).

---

## Step 1: System Requirements and Folder Skeleton
**Engineer Prompt:**
> "I need to build a single-container Trade Store application in Python 3.12 using Domain-Driven Design and Hexagonal Architecture (Ports and Adapters).
> 
> Core Business Requirements:
> 1. Ingest trades with attributes: Trade ID, Version, Counter-Party ID, Book ID, Maturity Date, Created Date, Expired flag.
> 2. Maturity Validation: Reject trades if maturity_date < today.
> 3. Version Validation: Reject incoming trades if version < stored_version. Overwrite existing records if version == stored_version. Insert new records if version > stored_version.
> 4. Auto-Expiration: A background job must periodically mark active trades (Expired = 'N') as expired (Expired = 'Y') when maturity_date < today.
> 5. Tech Stack: FastAPI, SQLite (via SQLAlchemy 2.0), in-memory version state cache, and an in-process streaming event queue (asyncio.Queue).
> 
> Review my proposed architecture and generate a clean project folder layout."

**AI Assistance Output:**
* Validated Hexagonal Architecture pattern (isolating domain, services, adapters, and api).
* Generated initial directory structure and requirements.txt manifest.

---

## Step 2: Domain Entity, Port Interfaces, and DTOs
**Engineer Prompt:**
> "Here are my domain requirements:
> - Entity: Trade dataclass in app/domain/models.py with is_expired() and mark_expired() methods.
> - Custom Exceptions: LowerVersionTradeException and InvalidMaturityDateException in app/domain/exceptions.py.
> - Abstract Ports: ITradeRepository, ITradeStateCache, and IEventQueue in app/domain/ports.py.
> - Pydantic DTOs: TradeRequest, TradeResponse, and ExceptionRecordResponse in app/api/schemas.py.
> 
> Generate Python stubs and abstract base classes for these interfaces."

**AI Assistance Output:**
* Produced stubbed abstract classes using abc.ABC and abc.abstractmethod.
* Defined Pydantic models with type annotations and example metadata for OpenAPI docs.

---

## Step 3: Test-Driven Development (TDD) Test Matrix
**Engineer Prompt:**
> "Review my test matrix for unit and integration testing:
> 1. test_successful_new_trade_ingestion: Ingests valid trade T1 v1 with future maturity date.
> 2. test_reject_lower_version_trade: Ingests T2 v2, then verifies T2 v1 is rejected with LowerVersionTradeException.
> 3. test_same_version_replaces_existing_record: Ingests T1 v1, then ingests updated T1 v1 and asserts fields are overwritten.
> 4. test_reject_trade_with_past_maturity_date: Asserts InvalidMaturityDateException when maturity_date < today.
> 5. test_auto_expiration_job: Verifies background job updates matured records to Expired = 'Y'.
> 6. test_api_endpoints: Integration test verifying HTTP 201, 400, 422, streaming queue, and exception log endpoints.
> 
> Generate the test boilerplate using Python unittest.IsolatedAsyncioTestCase."

**AI Assistance Output:**
* Generated test scaffolding and conftest.py fixtures setting up an in-memory SQLite database connection.

---

## Step 4: Logic Review and Concurrency Inspection
**Engineer Prompt:**
> "I have implemented the business logic in app/services/trade_service.py and the adapters (app/adapters/sqlite_repo.py, app/adapters/memory_cache.py, app/adapters/event_queue.py, app/adapters/exception_logger.py).
> 
> Review my implementation for:
> 1. Concurrency locks in InMemoryTradeStateCache and ExceptionLogger.
> 2. Thread safety when running synchronous SQLAlchemy SQLite calls from async handlers using asyncio.to_thread.
> 3. Edge cases where created_date might be missing or None."

**AI Review Feedback and Human Refinements:**
* Confirmed thread safety using asyncio.Lock in memory adapters.
* Verified asyncio.to_thread wraps synchronous SQLAlchemy session execution cleanly.
* Added fallback guards (created_date = trade.created_date or date.today()) in domain models and ORM adapters.

---

## Step 5: Kubernetes Persistence and PVC Deployment
**Engineer Prompt:**
> "I need to ensure that when deployed to Kubernetes, the SQLite database (trade_store.db), exception audit logs (exceptions.json), and application logs (app.log) persist across Pod restarts or rescheduling.
> 
> Review how environment variables DB_PATH, EXCEPTION_LOG_PATH, and LOG_PATH can be bound to a Kubernetes PersistentVolumeClaim (PVC) mounted at /data, and generate candidate k8s-deployment.yaml and docker-compose.yml manifests."

**AI Assistance Output:**
* Generated Kubernetes manifest (k8s-deployment.yaml) defining a 1Gi PersistentVolumeClaim (trade-store-pvc), Deployment mounting /data, and NodePort Service.
* Generated docker-compose.yml mapping named local volume trade-data to /data.

---

## Step 6: Single-Prompt Frontend Control Panel Generation
**Engineer Prompt:**
> "I want to generate the complete frontend interface (static/index.html) using AI only by defining the exact UI/UX and functional requirements in a single comprehensive prompt.
> 
> Frontend Prompt Specification:
> 'Create a single-file, dark-themed HTML/JS control panel (static/index.html) to interactively test and monitor the Trade Store application. The UI must include:
> 1. Header Metrics Bar: Live health dot, SQLite connection status, DB trade count, Queue depth, Exception count, Consumer state.
> 2. Ingestion Form Card: Radio toggle for Sync API vs Async Streaming Queue mode, Trade ID with a Random generator button and auto-randomize option, version, CP ID, book ID, maturity date.
> 3. Validation Test Scenarios Card: One-click buttons to run test scenarios (Pre-fill Valid Trade, Test Lower Version Rule HTTP 422, Test Past Maturity Rule HTTP 400, Configurable Batch Stream Generator with Batch Size N).
> 4. Real-time Event Queue Panel: Pause, Slow Speed (0.8s), and Real-time (0.0s) consumer controls, and a table showing pending queued trade events.
> 5. Database and Audit Tables: Live table of stored trades (with Show Expired toggle), and Rejections Audit Log table with clear button.
> 6. Interactive Documentation and Architecture Diagrams Viewer: Tabbed modal / drawer to view README.md, AI_PROMPTS.md, PlantUML diagrams (architecture.puml, domain_class.puml, trade_flow.puml), and live application logs (/data/app.log).'
> 
> Generate the complete static/index.html file using pure HTML5, CSS3, and Vanilla JavaScript with zero build dependencies."

**AI Generation Output:**
* Generated the complete single-page application (static/index.html) implementing all requested form controls, monitoring tables, documentation tabs, and PlantUML diagram viewers.

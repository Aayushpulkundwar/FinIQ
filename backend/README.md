# FinsightAI Backend

FinsightAI is a production-ready, clean-architecture backend for an AI-powered investment research platform. It is built using FastAPI, PostgreSQL, SQLAlchemy 2.0, Celery, Redis, LangChain, LangGraph, and pgvector.

## Architecture

This project is organized according to **Clean Architecture** patterns to enforce separation of concerns and scaling:

```
backend/
├── alembic/              # Database migration version files and env config
├── app/
│   ├── api/              # HTTP routers layer (Endpoints, versioning, routing)
│   ├── core/             # Base configurations, exceptions, logging, task workers
│   ├── db/               # ORM session configuration, base registries
│   ├── models/           # SQLAlchemy DB entities
│   ├── schemas/          # Pydantic v2 schemas for request/response serialization
│   ├── repositories/     # Data Access layer (Encapsulates SQLAlchemy logic)
│   ├── services/         # Business Logic layer (Coordinates entities and workflows)
│   ├── ai/               # Orchestrator, Agents (LangGraph), Tools, Prompts, and Memory
│   ├── rag/              # Loaders, Parsers, Chunking, Embeddings, Retrievers, Vector Stores
│   └── main.py           # Application Entrypoint (Middlewares, routers mounting)
├── tests/                # Unit and Integration test suite
├── Dockerfile            # Container configuration for FastAPI
├── docker-compose.yml    # Development multi-container orchestration manifest
├── requirements.txt      # Dependency specification
└── .env.example          # Sample environment configuration template
```

---

## Technical Stack & Configuration

- **FastAPI**: Main web framework.
- **SQLAlchemy 2.0**: Utilizing modern asynchronous select queries and Mapped mappings.
- **Alembic**: Async migrations configured through `alembic/env.py`.
- **Loguru**: Centralized logging capturing standard logging formats and outputs.
- **Celery & Redis**: Task orchestration and background jobs engine.
- **Docker & Compose**: Hot-reload workspace mount configurations and pgvector database image integrations.
- **Pytest**: Unit testing framework mock configurations with AsyncIO support.

---

## Getting Started

### Local Development Setup

1. **Clone & Set Up Env**:
   ```bash
   cp .env.example .env
   ```

2. **Run Backing Services with Docker Compose**:
   ```bash
   docker compose up --build
   ```
   This will boot:
   - FastAPI Backend at `http://localhost:8000`
   - Postgres DB (with pgvector) at port `5432`
   - Redis at port `6379`
   - Celery asynchronous worker

3. **Database Migrations**:
   Generate structural migrations:
   ```bash
   alembic revision --autogenerate -m "initial_schema"
   ```
   Apply migrations:
   ```bash
   alembic upgrade head
   ```

### Running Tests

Run the test suite using `pytest`:
```bash
pytest
```
This tests routers using dynamic database session mocks over asynchronous clients.

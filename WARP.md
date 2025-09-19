# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development Commands

### Local Development Setup
```bash
# Create virtual environment and install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start local PostgreSQL (using Docker)
docker-compose up postgres -d

# Run database migrations
alembic upgrade head

# Start Azure Functions runtime locally
func start
```

### Database Operations
```bash
# Create new migration after model changes
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Connect to local database
psql "postgresql+psycopg2://carai_user:carai_pass@localhost:5432/carai"
```

### Azure Functions Commands
```bash
# Start local development server
func start

# Deploy to Azure (requires Azure CLI setup)
func azure functionapp publish <function-app-name>

# View local function diagnostics
curl http://localhost:7071/api/_diag
```

## Project Architecture

### Core Structure
This is an Azure Functions (Python 3.11) application with a modular architecture:

- **`function_app.py`** - Main entry point that registers all HTTP triggers from route blueprints
- **`routes/`** - HTTP endpoint blueprints (auth, vehicles, diagnose, conversation)
- **`services/`** - Business logic layer (conversation, vehicle, blob storage, etc.)
- **`models/`** - SQLAlchemy ORM models for database entities
- **`auth/`** - JWT-based authentication system with email/PIN verification
- **`utils/`** - Cross-cutting concerns (CORS, PDF generation, etc.)

### Database Architecture
Uses **PostgreSQL** with **SQLAlchemy 2.x** and **Alembic** migrations:

- **Users** - Email-based authentication with password hashing
- **Vehicles** - User-owned vehicles with make/model/year + modifications
- **Conversations** - AI diagnostic conversations linked to specific vehicles
- **Messages** - Individual messages within conversations (user/assistant pairs)
- **Services** - Vehicle maintenance records with document attachments
- **EmailVerification** - Time-limited PINs for signup/password reset

Key architectural pattern: Each conversation is bound to a specific vehicle for context.

### AI Integration
- **OpenAI GPT-4o-mini** for automotive diagnostics
- **System prompts** tuned for mechanic-to-mechanic communication style
- **Conversation limits**: 20 conversations/month, 50 messages per conversation
- **Multimodal support**: Text, images, and audio transcription via OpenAI Whisper

### Azure Services Integration
- **Azure Blob Storage** - Document and image storage with SAS URL access
- **Azure Functions** - Serverless HTTP endpoints with Blueprint pattern
- **Azure PostgreSQL Flexible Server** - Primary database (production)

### Authentication Flow
1. User requests email verification PIN via `/api/request_pin`
2. PIN verification and account creation via `/api/confirm_signup`
3. Login returns JWT bearer token via `/api/login`
4. Protected endpoints validate JWT in Authorization header

### Route Structure
- **`/api/auth/*`** - Authentication (signup, login, password reset)
- **`/api/vehicles/*`** - Vehicle CRUD operations and modifications
- **`/api/diagnose2`** - Vehicle-specific AI diagnostics (preferred)
- **`/api/diagnose`** - Legacy diagnostics endpoint
- **`/api/conversations/*`** - Conversation history management

## Development Guidelines

### Environment Setup
- Use `.venv` for Python virtual environment
- Local development uses Docker Compose for PostgreSQL
- Environment variables loaded from `local.settings.json` (Azure Functions) or `.env` (local)
- Azure production uses managed identity for Blob Storage (preferred over connection strings)

### Database Patterns
- **No database-generated UUIDs** - SQLAlchemy generates UUIDs in Python (Azure Postgres compatibility)
- **Cascade deletes** properly configured for user → vehicles → conversations
- **Connection pooling** configured in `db.py` with pre-ping validation
- Use `SessionLocal()` context manager for database operations

### Error Handling
- All endpoints return structured JSON errors with appropriate HTTP status codes
- Rate limiting implemented via conversation/message limits (returns 402 Payment Required)
- CORS enabled for all endpoints via `utils.cors.cors_response()`

### Code Organization
- **Blueprint pattern** - Each route module exports `bp = func.Blueprint()` 
- **Service layer** - Business logic separated from HTTP handling
- **Dependency injection** - `current_user_from_request()` for auth in routes
- **Type hints** used throughout for better IDE support

### Testing & Quality
- No automated tests currently present
- Manual testing via `curl` or function app diagnostics endpoint
- Azure Functions provides built-in logging and monitoring

### Security Notes
- JWT tokens have 60-minute expiration
- Passwords hashed with bcrypt
- No extensions required in PostgreSQL (UUIDs generated in application)
- User preferences honored: Azure SQL Server over on-premises SQL Server, csharpier for formatting

### Azure Deployment Notes
- Uses consumption plan for cost efficiency
- Managed identity recommended for blob storage access
- Private networking setup available via VNet integration
- App Insights integrated for monitoring and logging

## Common Patterns

### Adding New Routes
1. Create blueprint in `routes/new_endpoint.py`
2. Register in `function_app.py` with `_try("routes.new_endpoint", "name")`
3. Use `@bp.function_name()` and `@bp.route()` decorators
4. Handle OPTIONS for CORS with `cors_response(204)`

### Database Operations
```python
with SessionLocal() as db:
    # Query operations
    result = db.query(Model).filter(...).first()
    # Write operations
    db.add(new_object)
    db.commit()
```

### Authentication Required
```python
user = current_user_from_request(req)
if not user:
    return cors_response("Unauthorized", 401)
```
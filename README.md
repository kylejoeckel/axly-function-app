# AXLY.pro — Backend API

Python Azure Functions backend for the AXLY.pro mobile app. Handles authentication, vehicle management, diagnostics, and subscription services.

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Local Setup](#local-setup)
6. [Environment Variables](#environment-variables)
7. [Database & Migrations](#database--migrations)
8. [Deployment](#deployment)
9. [API Endpoints](#api-endpoints)

---

## Overview

AXLY.pro backend provides:
- **Authentication** — JWT-based auth with email/password and Apple receipt validation
- **Vehicle Management** — CRUD for user vehicles with image uploads
- **Diagnostics** — AI-powered vehicle diagnostic analysis
- **Subscriptions** — Apple App Store subscription validation and management
- **Track Results** — Performance timing data storage

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.11, Azure Functions v4 |
| Database | PostgreSQL 15 (Azure Flexible Server) |
| ORM | SQLAlchemy 2.x + Alembic migrations |
| Auth | JWT (HMAC-SHA256) |
| AI | OpenAI GPT-4o-mini |
| Storage | Azure Blob Storage |
| Email | SMTP (Gmail) |

---

## Project Structure

```
├── routes/
│   ├── auth.py           # Login, signup, password reset
│   ├── vehicles.py       # Vehicle CRUD, image upload
│   ├── diagnose.py       # AI diagnostics
│   ├── subscriptions.py  # App Store subscription handling
│   └── track_results.py  # Performance timing data
├── models/               # SQLAlchemy models
├── services/             # Business logic
├── alembic/              # Database migrations
├── utils/                # Helpers (jwt, email, etc.)
├── db.py                 # Database connection
├── function_app.py       # Azure Functions entry point
└── requirements.txt
```

---

## Prerequisites

- Python 3.11
- Azure Functions Core Tools v4 (`npm i -g azure-functions-core-tools@4`)
- PostgreSQL 13+ (local or Docker)
- Azure CLI (`az`)

---

## Local Setup

```bash
# Clone and setup
git clone <repo-url>
cd diagcar-backend-py

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp local.settings.example.json local.settings.json
# Edit local.settings.json with your values

# Run migrations
alembic upgrade head

# Start local server
func start
```

Server runs at `http://localhost:7071`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret key for JWT signing |
| `OPENAI_API_KEY` | OpenAI API key |
| `SMTP_HOST` | SMTP server (default: smtp.gmail.com) |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username/email |
| `SMTP_PASS` | SMTP password or app password |
| `EMAIL_FROM` | From email address |
| `APP_STORE_SHARED_SECRET` | Apple App Store shared secret |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob storage connection |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins |

---

## Database & Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback one migration
alembic downgrade -1

# View current revision
alembic current
```

**Note:** UUIDs are generated in application code (not DB extensions) for Azure compatibility.

---

## Deployment

### GitHub Actions (CI/CD)

Deployments are automated via GitHub Actions:
- **Dev:** Push to `dev` branch → deploys to `fa-axlypro-dev`
- **Prod:** Push to `main` branch → deploys to `fa-axlypro-prod`

Migrations run automatically after deployment.

### Manual Deployment

```bash
# Deploy to Azure
func azure functionapp publish <function-app-name>
```

---

## API Endpoints

### Auth
- `POST /api/login` — Email/password login
- `POST /api/confirm_signup` — Create account with PIN verification
- `POST /api/request_pin` — Request email verification PIN
- `POST /api/auth/receipt` — Apple receipt authentication
- `POST /api/auth/refresh` — Refresh access token

### Vehicles
- `GET /api/vehicles` — List user vehicles
- `POST /api/vehicles` — Create vehicle
- `GET /api/vehicles/{id}` — Get vehicle details
- `PUT /api/vehicles/{id}` — Update vehicle
- `DELETE /api/vehicles/{id}` — Delete vehicle
- `POST /api/vehicles/{id}/image` — Upload vehicle image

### Diagnostics
- `POST /api/diagnose` — AI diagnostic analysis

### Subscriptions
- `GET /api/subscriptions/status` — Get subscription status
- `POST /api/subscriptions/refresh` — Refresh subscription from App Store

### Track Results
- `GET /api/track-results` — List track results
- `POST /api/track-results` — Save track result
- `DELETE /api/track-results/{id}` — Delete track result

---

## License

Copyright 2025 AXLY.pro. All rights reserved.

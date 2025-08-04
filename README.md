# Axly.pro — Azure Functions Back‑End

Comprehensive README covering local development, Azure deployment, database schema + migrations, and relevant environment variables.

---

## Table of Contents

1. [Overview](#overview)
2. [Function App Structure](#function-app-structure)
3. [Prerequisites](#prerequisites)
4. [Local Setup](#local-setup)
5. [Environment Variables](#environment-variables)
6. [Database Schema](#database-schema)
7. [Schema Migrations](#schema-migrations)
8. [Running Tests](#running-tests)
9. [CI / CD Pipeline](#ci-cd-pipeline)
10. [Operations & Observability](#operations--observability)
11. [License](#license)

---

## 1  Overview

* **Runtime** — Python 3.11 · Azure Functions **v4**
* **Database** — Azure PostgreSQL Flexible Server (or any Postgres ≥ 13)
* **ORM** — SQLAlchemy 2.x + **Alembic** migrations
* **AI Provider** — OpenAI gpt‑4o‑mini (via `openai` Python SDK)
* **Auth** — Stateless JWT (HMAC‑SHA256) with e‑mail + PIN verification
* **Asset Storage** — User‑supplied images/audio are passed as Base‑64 (no blob storage yet).

---

## 2  Function App Structure

```
api/
│
├─ routes/
│   ├─ auth.py            # /login /request_pin /confirm_signup …
│   ├─ vehicles.py        # /vehicles CRUD + /{id}/mods
│   ├─ diagnose.py        # /Diagnose  (legacy + v2)
│   └─ __init__.py        # Blueprint registry
│
├─ services/              # Business logic (email, vehicles, parser …)
├─ models.py              # SQLAlchemy models
├─ db.py                  # SessionLocal & engine factory
├─ alembic/               # Migrations (versions/ env.py)
├─ utils/                 # cors_response, hashing, audio utils
└─ host.json / local.settings.json
```

---

## 3  Prerequisites

* **Python 3.11**
* **Azure Functions Core Tools v4** (`npm i -g azure-functions-core-tools@4`)
* **PostgreSQL 13+** locally (Docker is fine)
* **Node 18** (only for tests that hit OpenAI via nock)
* **Migrator** — `alembic` (auto‑installed via `requirements.txt`)

---

## 4  Local Setup

```bash
# 1. Clone
git clone https://github.com/YourOrg/axly-pro-api.git
cd axly-pro-api/api

# 2. Create & activate venv
python -m venv .venv && source .venv/bin/activate

# 3. Install deps
pip install -r requirements.txt

# 4. Configure local.settings.json
cp local.settings.example.json local.settings.json
# → fill in DB_URI, OPENAI_KEY …

# 5. Run migrations (creates tables)
alembic upgrade head

# 6. Start Functions host
func start

# 7. Hit http://localhost:7071/api/health  (returns 200 OK)
```

---

## 5  Environment Variables

| Key                    | Description                        | Example                                              |
| ---------------------- | ---------------------------------- | ---------------------------------------------------- |
| `DB_URI`               | Postgres connection string.        | `postgresql+psycopg://axly:pass@localhost:5432/axly` |
| `JWT_SECRET`           | HMAC secret for signing tokens.    | `super‑secret‑string`                                |
| `OPENAI_API_KEY`       | Key for gpt‑4o‑mini.               | **keep private**                                     |
| `PIN_EXP_MINUTES`      | Minutes before e‑mail PIN expires. | `15`                                                 |
| `CORS_ALLOWED_ORIGINS` | Comma‑sep list.                    | `http://localhost:19006,https://app.axly.pro`        |
| `SENDGRID_KEY`         | Optional – transactional e‑mail.   |                                                      |

In Azure set these in **Configuration → Application settings**; Core Tools
pulls them automatically from `local.settings.json` during local runs.

---

## 6  Database Schema

*(Initial schema = Alembic revision `01_initial.py`)*

```sql
-- users
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- email verification
CREATE TABLE email_verification (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  pin TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- vehicles
CREATE TABLE vehicles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- vehicle modifications
CREATE TABLE vehicle_mods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  installed_on DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  vehicle_id UUID REFERENCES vehicles(id),
  title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- chat messages
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('user','assistant')),
  content JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Indexes & Constraints

```sql
CREATE INDEX ix_vehicle_user ON vehicles(user_id);
CREATE INDEX ix_conv_user    ON conversations(user_id);
CREATE INDEX ix_msg_conv     ON chat_messages(conversation_id);
```

---

## 7  Schema Migrations

| Revision ID               | Date       | Summary                                                  |
| ------------------------- | ---------- | -------------------------------------------------------- |
| **01\_initial**           | 2025‑06‑01 | users · vehicles · conversations · email\_verification   |
| **02\_vehicle\_mods**     | 2025‑06‑15 | `vehicle_mods` table + FK cascade                        |
| **03\_conv\_vehicle\_fk** | 2025‑07‑10 | add `vehicle_id` nullable FK to conversations            |
| **04\_chat\_messages**    | 2025‑07‑20 | new `chat_messages` table; dropped `history_json` column |

Apply manually:

```bash
alembic upgrade head        # to latest
alembic downgrade -1        # roll back one
alembic revision --autogenerate -m "new change"
```

---

## 8  Running Tests

```bash
pytest -q            # unit tests
pytest -m integration  # marks integration (hits DB + OpenAI mock)
```

* Uses `pytest-asyncio` + `httpx` test client for function triggers.
* DB spins up in Docker via `pytest-postgresql` if `TEST_DB_URI` not set.

---

## 9  CI / CD Pipeline

| Stage                  | Tool                             | Notes                                                             |
| ---------------------- | -------------------------------- | ----------------------------------------------------------------- |
| **Lint + Unit Tests**  | GitHub Actions (`python‑ci.yml`) | runs `ruff`, `pytest`, coverage gate ≥ 90 %                       |
| **Build**              | `func azure functionapp publish` | Executes in `--build-native-deps` mode                            |
| **DB Schema**          | Alembic                          | `alembic upgrade head` runs inside Azure Web App start‑up command |
| **Prod Observability** | Azure App Insights               | `APPINSIGHTS_INSTRUMENTATIONKEY` set in Settings                  |

---

## 10  Operations & Observability

* **Logs** – Stream with `func azure functionapp logstream <name>`
* **Metrics** – App Insights custom events (`diagnose_duration_ms`, `openai_tokens`)
* **Alert Rules** – 5XX > 1 % or DB CPU > 70 % for 10 min triggers Slack webhook.
* **Secrets Rotation** – Use Azure Key Vault references instead of raw settings.

---

## 11  License

```
Apache‑2.0
Copyright 2025 Axly
```

---

### Quick Copy‑Paste for Fresh Dev DB

```bash
docker run --name axly-pg -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=axly \
  -p 5432:5432 -d postgres:15
export DB_URI=postgresql+psycopg://postgres:pass@localhost:5432/axly
alembic upgrade head
```

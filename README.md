Awesome call. Here’s an updated README with a new, copy-pasteable **Infrastructure (Azure)** section (DB + Blob + Function App), plus env var updates and a tiny appendix Terraform starter. Drop this in your README (it replaces/augments what you have).

---

# Axly.pro — Azure Functions Back-End

Comprehensive README covering local development, Azure deployment, database schema + migrations, environment variables, and production infrastructure.

---

## Table of Contents

1. [Overview](#overview)
2. [Function App Structure](#function-app-structure)
3. [Prerequisites](#prerequisites)
4. [Local Setup](#local-setup)
   4a. [Infrastructure (Azure): DB + Blob + Function App](#infrastructure-azure-db--blob--function-app)
5. [Environment Variables](#environment-variables)
6. [Database Schema](#database-schema)
7. [Schema Migrations](#schema-migrations)
8. [Running Tests](#running-tests)
9. [CI / CD Pipeline](#ci--cd-pipeline)
10. [Operations & Observability](#operations--observability)
11. [License](#license)
    A1. [Appendix: Terraform Starter (Optional)](#appendix-terraform-starter-optional)

---

## 1  Overview

* **Runtime** — Python 3.11 · Azure Functions **v4**
* **Database** — Azure PostgreSQL Flexible Server (or any Postgres ≥ 13)
* **ORM** — SQLAlchemy 2.x + **Alembic** migrations
* **AI Provider** — OpenAI gpt-4o-mini (via `openai` Python SDK)
* **Auth** — Stateless JWT (HMAC-SHA256) with e-mail + PIN verification
* **Asset Storage** — Azure **Blob Storage** (containers for user assets, receipts, mod docs)

---

## 2  Function App Structure

```
api/
│
├─ routes/
│   ├─ auth.py
│   ├─ vehicles.py
│   ├─ diagnose.py
│   └─ __init__.py
│
├─ services/
├─ models/                 # SQLAlchemy models split by domain
├─ db.py                   # SessionLocal & engine factory
├─ alembic/
├─ utils/
└─ host.json / local.settings.json
```

---

## 3  Prerequisites

* Python 3.11
* Azure CLI (`az`) and **Azure Functions Core Tools v4** (`npm i -g azure-functions-core-tools@4`)
* PostgreSQL 13+ (Docker is fine)
* Node 18 (only if you run certain tests)

---

## 4  Local Setup

```bash
git clone https://github.com/YourOrg/axly-pro-api.git
cd axly-pro-api/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp local.settings.example.json local.settings.json
alembic upgrade head
func start
```

---

## 4a  Infrastructure (Azure): DB + Blob + Function App

> Production-ready baseline using Azure CLI. Names are examples; change to your own.

### 4a.1 Resource Group

```bash
LOCATION=centralus
RG=axly-prod-rg
az group create -n $RG -l $LOCATION
```

### 4a.2 Storage for Functions Runtime (AzureWebJobsStorage)

```bash
FUNCSTG=axlyfuncstgprod$RANDOM
az storage account create -g $RG -n $FUNCSTG -l $LOCATION --sku Standard_LRS --kind StorageV2
FUNCSTG_CONN=$(az storage account show-connection-string -g $RG -n $FUNCSTG --query connectionString -o tsv)
```

### 4a.3 App Insights

```bash
APPINS=axly-ai-prod
az monitor app-insights component create -g $RG -l $LOCATION -a $APPINS --application-type web
APPINS_KEY=$(az monitor app-insights component show -g $RG -a $APPINS --query instrumentationKey -o tsv)
```

### 4a.4 Azure Function App (Python 3.11, Linux Consumption)

```bash
FUNCNAME=axly-api-prod
az functionapp create \
  --resource-group $RG \
  --consumption-plan-location $LOCATION \
  --runtime python --runtime-version 3.11 \
  --functions-version 4 \
  --name $FUNCNAME \
  --storage-account $FUNCSTG
az functionapp config appsettings set -g $RG -n $FUNCNAME --settings \
  AzureWebJobsStorage="$FUNCSTG_CONN" \
  APPINSIGHTS_INSTRUMENTATIONKEY="$APPINS_KEY"
```

### 4a.5 Asset Storage (Blob) + Containers

```bash
ASSETSTG=axlyassetsprod$RANDOM
az storage account create -g $RG -n $ASSETSTG -l $LOCATION --sku Standard_LRS --kind StorageV2
ASSET_ID=$(az storage account show -g $RG -n $ASSETSTG --query id -o tsv)

# Use AAD auth via Managed Identity (recommended)
az functionapp identity assign -g $RG -n $FUNCNAME
PRINCIPAL_ID=$(az functionapp identity show -g $RG -n $FUNCNAME --query principalId -o tsv)
az role assignment create --assignee $PRINCIPAL_ID --role "Storage Blob Data Contributor" --scope $ASSET_ID

# Create containers
az storage container create --name mod-documents     --account-name $ASSETSTG --auth-mode login
az storage container create --name service-documents --account-name $ASSETSTG --auth-mode login
az storage container create --name diagnose-uploads  --account-name $ASSETSTG --auth-mode login

# App settings for asset storage (AAD auth)
ASSETS_URL="https://$ASSETSTG.blob.core.windows.net"
az functionapp config appsettings set -g $RG -n $FUNCNAME --settings \
  ASSETS_BLOB_ACCOUNT_URL="$ASSETS_URL" \
  ASSETS_CONTAINER_MOD_DOCS="mod-documents" \
  ASSETS_CONTAINER_SERVICE_DOCS="service-documents" \
  ASSETS_CONTAINER_UPLOADS="diagnose-uploads"
```

> If you prefer connection strings instead of AAD, create a key and set `ASSETS_BLOB_CONNECTION` instead of `ASSETS_BLOB_ACCOUNT_URL`. AAD via Managed Identity is recommended.

### 4a.6 Azure PostgreSQL Flexible Server

> UUID extensions (`uuid-ossp`, `pgcrypto`) are often **not allow-listed**. We rely on **app-generated UUIDs** (SQLAlchemy `default=uuid.uuid4`), so **no DB extensions required**.

```bash
PGNAME=axlypg-prod
PGUSER=axlyadmin
PGPASS='REPLACE_ME_STRONG'          # store in Key Vault later
PGDB=axly

az postgres flexible-server create \
  --resource-group $RG \
  --name $PGNAME \
  --location $LOCATION \
  --version 15 \
  --tier GeneralPurpose --sku-name Standard_D2s_v5 \
  --storage-size 128 \
  --administrator-user $PGUSER \
  --administrator-login-password "$PGPASS" \
  --yes

# Create database
az postgres flexible-server db create -g $RG -s $PGNAME -d $PGDB

# Allow temporary public access from your IP (for initial migration); remove later
MYIP=$(curl -s https://api.ipify.org)
az postgres flexible-server firewall-rule create -g $RG -s $PGNAME -n allow-my-ip --start-ip-address $MYIP --end-ip-address $MYIP
```

Connection string (SQLAlchemy):

```
postgresql+psycopg://axlyadmin:REPLACE_ME_STRONG@${PGNAME}.postgres.database.azure.com:5432/${PGDB}?sslmode=require
```

Set it on the Function App:

```bash
DB_URI="postgresql+psycopg://$PGUSER:$PGPASS@$PGNAME.postgres.database.azure.com:5432/$PGDB?sslmode=require"
az functionapp config appsettings set -g $RG -n $FUNCNAME --settings DB_URI="$DB_URI"
```

> Recommended: store `DB_URI`/`OPENAI_API_KEY` in **Azure Key Vault** and reference them in App Settings.

### 4a.7 Run Migrations Against Prod

```bash
# from your workstation (same DB_URI as app)
export DB_URI="postgresql+psycopg://$PGUSER:$PGPASS@$PGNAME.postgres.database.azure.com:5432/$PGDB?sslmode=require"
alembic upgrade head
```

### 4a.8 Lock Down Networking (Recommended)

Option A — keep public with strict allowlist:

```bash
# remove "AllowAllWindowsAzureIps" if present
az postgres flexible-server firewall-rule delete -g $RG -s $PGNAME -n AllowAllWindowsAzureIps --yes
# restrict to VNet or to the Function NAT IPs only
```

Option B — Private access:

* Create a Private Endpoint for the Postgres server in a VNet.
* Integrate the Function App with that VNet (VNet Integration).
* Remove public access on Postgres:
  `az postgres flexible-server update -g $RG -n $PGNAME --public-network-access Disabled`

### 4a.9 Final App Settings

```bash
az functionapp config appsettings set -g $RG -n $FUNCNAME --settings \
  OPENAI_API_KEY="REPLACE" \
  JWT_SECRET="REPLACE" \
  PIN_EXP_MINUTES="15" \
  CORS_ALLOWED_ORIGINS="https://app.axly.pro"
```

### 4a.10 Verification

```bash
az functionapp show -g $RG -n $FUNCNAME --query state
curl https://$FUNCNAME.azurewebsites.net/api/health
psql "$DB_URI" -c "\dt"
```

---

## 5  Environment Variables

| Key                             | Description                                  | Example                                                         |
| ------------------------------- | -------------------------------------------- | --------------------------------------------------------------- |
| `DB_URI`                        | Postgres connection string                   | `postgresql+psycopg://user:pass@host:5432/axly?sslmode=require` |
| `JWT_SECRET`                    | HMAC secret                                  | `super-secret-string`                                           |
| `OPENAI_API_KEY`                | Key for OpenAI                               |                                                                 |
| `PIN_EXP_MINUTES`               | Minutes before e-mail PIN expires            | `15`                                                            |
| `CORS_ALLOWED_ORIGINS`          | Comma-sep list                               | `https://app.axly.pro`                                          |
| `SENDGRID_KEY`                  | Optional – transactional e-mail              |                                                                 |
| `AzureWebJobsStorage`           | **Required** by Functions runtime            | Storage account connection string                               |
| `ASSETS_BLOB_ACCOUNT_URL`       | Asset storage account URL (AAD auth)         | `https://axlyassetsprod.blob.core.windows.net`                  |
| `ASSETS_BLOB_CONNECTION`        | Asset storage connection string (alt to AAD) |                                                                 |
| `ASSETS_CONTAINER_MOD_DOCS`     | Container for mod docs                       | `mod-documents`                                                 |
| `ASSETS_CONTAINER_SERVICE_DOCS` | Container for service docs                   | `service-documents`                                             |
| `ASSETS_CONTAINER_UPLOADS`      | Container for uploads                        | `diagnose-uploads`                                              |

> Azure Postgres: **no extensions required**. We generate UUIDs in app code.

---

## 6  Database Schema

> Migrations define the live schema. UUID columns are created **without** DB-side UUID defaults on Azure; SQLAlchemy assigns UUIDs.

*(example tables omitted for brevity)*

---

```bash
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "new change"
```

**Azure Postgres notes**

* Do **not** use `CREATE EXTENSION "uuid-ossp"` or `pgcrypto` in migrations.
* Ensure `server_default` for UUIDs is not set to DB functions; rely on model defaults.

---

## 7  CI / CD Pipeline

| Stage             | Tool                            | Notes                                               |
| ----------------- | ------------------------------- | --------------------------------------------------- |
| Build & Deploy    | GitHub Actions + `func publish` | Deploy to `$FUNCNAME`                               |

---

## License

```
Apache-2.0
Copyright 2025 Axly
```





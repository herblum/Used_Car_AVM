# UC_AVM — Architecture Plan

## Status: MVP COMPLETE

## Goal
Design a minimalist, scalable architecture for a mobile app that:
1. Lets users input car features (make, model, year, km, etc.)
2. Returns a predicted price range
3. Re-scrapes MercadoLibre and retrains the ML model every ~2 weeks

---

## Architecture Overview

```
┌─────────────┐      HTTPS       ┌──────────────────┐       ┌──────────────┐
│  Mobile App  │ ◄──────────────► │   API Gateway /  │ ────► │  ML Model    │
│  (Expo/RN)   │   REST JSON     │   Cloud Function │       │  (pickle on  │
└─────────────┘                  └──────────────────┘       │   S3/GCS)    │
                                         │                   └──────────────┘
                                         │ reads
                                         ▼
                                 ┌──────────────────┐
                                 │   SQLite / Turso  │
                                 │   (car listings   │
                                 │    + metadata)    │
                                 └──────────────────┘
                                         ▲
                                         │ writes
                                 ┌──────────────────┐
                                 │  Cron Job         │
                                 │  (scrape + train) │
                                 │  every 2 weeks    │
                                 └──────────────────┘
```

---

## Component Decisions

### 1. Mobile App — React Native (Expo)

**Choice**: Expo (React Native)
**Why**:
- Single codebase → iOS + Android (you're one developer)
- Expo handles builds, OTA updates, and app store submissions
- Huge ecosystem, easy to find help
- TypeScript for type safety
- The app is essentially a form + result display — no heavy native modules needed
- Expo Go for instant dev testing on your phone

**Alternatives rejected**:
- Flutter: great but smaller ecosystem, Dart has fewer ML/data libraries if needed
- Native (Swift/Kotlin): 2x the work for a simple form app
- PWA: works but worse UX, no app store presence, limited offline

**UI will be minimal**: one screen with a form (dropdowns + inputs), one screen with results (price range + confidence). That's it.

---

### 2. Backend API — Single Cloud Function (AWS Lambda or Google Cloud Function)

**Choice**: One serverless function behind an API Gateway
**Why**:
- You have ONE endpoint: `POST /predict` — that's it
- Serverless = $0 when idle, pennies when used. Perfect for MVP
- No server to manage, patch, or keep alive
- Cold starts are fine for this use case (~1-2s, user is submitting a form)
- Auto-scales to thousands of requests if needed (future-proofing)
- Python runtime — same language as your scraper and ML code

**Alternatives rejected**:
- Always-on server (EC2/VPS): paying 24/7 for an app that gets maybe 100 req/day initially
- FastAPI on a container: more flexible but overkill; you'd still need infrastructure
- Firebase Functions: works but locks you into Firebase ecosystem

**Framework**: Plain Python handler or lightweight FastAPI wrapped in Lambda (via Mangum adapter) if you want OpenAPI docs.

**The function will**:
1. Receive car features as JSON
2. Load the trained model (cached in memory across warm invocations)
3. Run inference
4. Return predicted price range + confidence interval

---

### 3. ML Model — LightGBM (Quantile Regression)

**Choice**: LightGBM with native categorical support
**Why**:
- Tabular data with 17 features → tree-based models dominate this domain
- LightGBM handles categoricals natively (no encoding needed) — better for high-cardinality features like `modelo` (71+ values)
- Handles NaN natively — no imputer needed
- Faster training than XGBoost (histogram-based, leaf-wise growth)
- Model serialized as `.joblib` file (~3.6 MB) — tiny, loads in milliseconds
- No GPU needed for inference

**Alternatives rejected**:
- XGBoost: similar performance but requires OrdinalEncoder + SimpleImputer for categoricals/nulls
- Deep learning (PyTorch/TF): massive overkill for tabular data
- Linear regression: too simple, can't capture non-linear price relationships

**Price range output**: 3 quantile models (q10, q50, q90) → predicts 10th, 50th, 90th percentile.

**Evaluation**: k-fold CV on training set + held-out 20% test set.

**Data preprocessing**:
- All prices normalized to USD (ARS ÷ 1400) before training
- Mislabeled currencies corrected (any price > 500K labeled as USD → fixed to ARS)
- IQR-based outlier filtering on USD-normalized prices
- Derived features (`vehiculo_edad`, `km_por_anio`) computed server-side, not user-input
- Target log-transformed (`y = log(price)`) before training; predictions are exponentiated back

**Trim level extraction** (`trim_extractor.py`):
- Extracts vehicle trim level (e.g., "Comfortline", "Titanium", "SRV") from the `version` string
- Three-tier strategy: brand-specific dictionary lookup → fallback tokenization → None (LightGBM handles missing natively)
- `trim_level` is a categorical feature passed to LightGBM at both training and inference time

**Features (17 total)**:
- Numeric (7): `anio`, `kilometros`, `vehiculo_edad`, `cilindrada_cc`, `puertas`, `km_por_anio`, `es_concesionario`
- Categorical (10): `marca`, `modelo`, `condicion`, `combustible`, `transmision`, `traccion`, `tipo_carroceria`, `color`, `provincia`, `trim_level`

**Current metrics (16,952 rows after IQR filter, from 18,328 in DB, retrained Apr 23 2026)**:

| Metric | Baseline (8.5K rows, no trim) | Current — q50 (16.9K rows + trim_level) |
|--------|-------------------------------|------------------------------------------|
| R²     | 0.81                          | **0.87**                                 |
| MAE    | $2,822                        | **$2,054**                               |
| MAPE   | 32.8%                         | **17.7%**                                |

- q10 model: MAE=$3,553, R²=0.667, MAPE=19.0%
- q90 model: MAE=$3,330, R²=0.777, MAPE=35.0%
- 5-fold CV (q50 on training set): MAE=$2,102, R²=0.871
- Improvements driven by: 2× more data + `trim_level` feature

**Model artifact**: Single `.joblib` file (~3.6 MB) containing 3 LightGBM models (q10, q50, q90).

---

### 4. Database — SQLite on Turso (or plain SQLite file)

**Choice**: Start with SQLite file, migrate to Turso (hosted SQLite) when needed
**Why**:
- Your data is tabular, structured, and relatively small (thousands of rows, not millions)
- SQLite is the simplest possible database — zero configuration
- Turso gives you hosted SQLite with HTTP API and edge replication when you need remote access
- The scraper writes to it, the training script reads from it — simple read/write pattern
- No connection pooling, no ORM complexity, no managed DB costs
- CSV → SQLite migration is trivial (pandas `to_sql()`)

**Alternatives rejected**:
- PostgreSQL (Supabase/RDS): real DB but overkill; you don't need concurrent writes, joins across tables, or ACID transactions
- MongoDB: document store adds complexity for fundamentally tabular data
- DynamoDB: wrong data model, expensive at scale for analytical reads
- Just keep CSV: works for scraping but bad for querying, no schema enforcement, append-only issues

**Schema** (single table):
```sql
CREATE TABLE listings (
    id            INTEGER PRIMARY KEY,
    item_id       TEXT UNIQUE NOT NULL,
    source_url    TEXT,
    marca         TEXT,
    modelo        TEXT,
    version       TEXT,
    anio          INTEGER,
    kilometros    REAL,
    condicion     TEXT,
    vehiculo_edad INTEGER,
    cilindrada_cc INTEGER,
    combustible   TEXT,
    transmision   TEXT,
    traccion      TEXT,
    tipo_carroceria TEXT,
    puertas       INTEGER,
    color         TEXT,
    precio        REAL,
    moneda        TEXT,
    es_concesionario INTEGER,
    provincia     TEXT,
    km_por_anio   REAL,
    scraped_at    TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);
```

---

### 5. Scheduled Pipeline — Cron Job (GitHub Actions or Cloud Scheduler)

**Choice**: GitHub Actions on a schedule (cron)
**Why**:
- Free for public repos, generous minutes for private repos
- Your scraper is already Python — just run it in CI
- No infrastructure to manage
- Built-in secrets management (for Firecrawl API key)
- Logs and history are automatically preserved
- Easy to trigger manually when needed

**The pipeline runs every 2 weeks**:
```
1. Run scraper (ml_scraper/) → new CSV data
2. Upsert new rows into SQLite DB (deduplicate by item_id)
3. Train new model on full dataset
4. Evaluate model (log metrics: MAE, RMSE, R²)
5. Upload new model artifact to cloud storage
6. (Optional) Send notification (Slack/email) with training report
```

**Alternatives rejected**:
- AWS EventBridge + Lambda: works but more setup for a 2-week cron
- Airflow/Dagster: full orchestrators — massive overkill for a 5-step pipeline
- Manual execution: error-prone, you'll forget

---

### 6. Cloud Storage — S3 or GCS bucket

**Choice**: Single cloud bucket for model artifacts
**Why**:
- Store versioned model files: `models/model-v1.joblib`, `models/model-v2.joblib`
- Lambda/Cloud Function loads latest model on cold start
- Dirt cheap ($0.023/GB/month on S3)
- Versioning lets you roll back if a retrained model performs worse

---

## Project Structure (proposed)

```
UC_AVM project/
├── CLAUDE.md
├── ml_scraper/              # ← EXISTING (scraper)
│   ├── scraper.py
│   ├── config.py
│   ├── parser.py
│   └── data/
├── ml_model/                # ← NEW (training + inference)
│   ├── train.py             # Training script (reads DB, outputs .joblib)
│   ├── predict.py           # Inference (loads model, returns price range, USD↔ARS conversion)
│   ├── evaluate.py          # Model evaluation metrics (MAE, RMSE, R², MAPE)
│   ├── features.py          # Feature definitions + dtype casting (no encoding/imputation needed)
│   ├── artifacts/            # Trained model files (.joblib, gitignored)
│   └── requirements.txt     # lightgbm, scikit-learn, pandas, joblib, numpy
├── api/                     # ← NEW (serverless function)
│   ├── handler.py           # Lambda/CF handler: POST /predict + GET /health (computes derived fields server-side)
│   ├── requirements.txt
│   └── template.yaml        # AWS SAM template
├── mobile/                  # ← NEW (Expo app, TypeScript)
│   ├── app/_layout.tsx      # Root layout (Stack navigator)
│   ├── app/index.tsx        # Form screen (car features input)
│   ├── app/results.tsx      # Results screen (price range display)
│   ├── lib/api.ts           # API client (configurable via EXPO_PUBLIC_API_URL)
│   ├── package.json
│   └── app.json
├── .github/workflows/
│   └── retrain.yml          # GitHub Actions cron (1st & 15th of each month)
├── pipeline/                # ← NEW (scheduled jobs)
│   └── run_pipeline.py      # Orchestrates: scrape → DB → train → upload
├── db/                      # ← NEW (database)
│   ├── schema.sql
│   ├── migrate.py           # CSV → SQLite migration
│   └── avm.db               # SQLite database (gitignored)
└── tasks/
    └── todo.md
```

---

## Data Flow (end to end)

```
Every 2 weeks (automated):
  MercadoLibre → [Scraper] → CSV → [Migrate] → SQLite DB → [Train] → model.joblib → S3

On user request (real-time):
  Mobile App → POST /predict {features} → [Lambda] → load model → inference → {price_range} → Mobile App
```

---

## Key Design Decisions Summary

| Decision | Choice | Why |
|----------|--------|-----|
| Mobile framework | Expo (React Native) | One codebase, simple form UI, easy deployment |
| API | Serverless function | One endpoint, $0 idle cost, auto-scales |
| ML model | LightGBM (quantile regression) | Native categorical/null handling, fast training, 3 quantile models |
| Database | SQLite (→ Turso later) | Simplest option for structured tabular data |
| Pipeline | GitHub Actions cron | Free, no infra, built-in secrets & logs |
| Model storage | S3/GCS bucket | Cheap, versioned, accessible from Lambda |
| Language | Python (backend) + TypeScript (mobile) | Matches existing code, strong ecosystems |

---

## Cost Estimate (MVP)

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (1000 req/day) | ~$0.20 |
| S3 (model storage) | ~$0.01 |
| API Gateway | ~$3.50 |
| GitHub Actions | Free tier |
| Turso (if used) | Free tier (500M rows read) |
| **Total** | **~$4/month** |

---

## What I'd Build First (implementation order)

- [x] 1. Set up SQLite DB + migration script (CSV → DB) — `db/schema.sql`, `db/migrate.py`
- [x] 2. Build ML training pipeline — `ml_model/features.py`, `ml_model/train.py`, `ml_model/evaluate.py` (LightGBM, k-fold CV + held-out test, 3 quantile models)
- [x] 3. Build prediction function — `ml_model/predict.py`
- [x] 4. Deploy serverless API — `api/handler.py`, `api/template.yaml` (FastAPI + Mangum/Lambda, derived fields computed server-side)
- [x] 5. Build Expo mobile app — `mobile/app/index.tsx` (form), `mobile/app/results.tsx` (results), `mobile/lib/api.ts`
- [x] 6. Set up GitHub Actions pipeline — `pipeline/run_pipeline.py`, `.github/workflows/retrain.yml` (biweekly cron)
- [x] 7. End-to-end testing — passed on 8.5K rows after IQR outlier filtering + currency normalization (R²=0.81, MAE=$2,822, MAPE=32.8%). Will improve with 100K rows.

---

## Environment Setup

- **Python**: conda environment `uc_avm` (Python 3.11) — LightGBM, scikit-learn, FastAPI, uvicorn
- **Node.js**: `mobile/node_modules/` (Expo 54, React Native, TypeScript)
- **Local testing**:
  - API: `conda activate uc_avm && uvicorn api.handler:app --host 0.0.0.0 --port 8000`
  - Mobile: `EXPO_PUBLIC_API_URL=http://<local-ip>:8000 npx expo start --tunnel`

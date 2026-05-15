# 🏠 Avito.ma Real Estate Data Pipeline & ML Platform

> A complete end-to-end industrial data pipeline built on Moroccan real estate listings scraped from Avito.ma — from raw scraping to BI dashboards and machine learning predictions.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Pipeline Layers](#pipeline-layers)
- [Data Warehouse](#data-warehouse)
- [Machine Learning](#machine-learning)
- [FastAPI](#fastapi)
- [Web Application](#web-application)
- [Power BI Dashboard](#power-bi-dashboard)
- [Setup & Run](#setup--run)
- [Compliance & Ethics](#compliance--ethics)

---

## Overview

This project implements a full industrial data pipeline that transforms raw Avito.ma real estate listings into a decision-ready architecture for both **Business Intelligence** (Power BI) and **Machine Learning** (price prediction & classification).

**Data collected:** 1,777 clean apartment listings across 6 Moroccan cities  
**Cities covered:** Casablanca · Rabat · Marrakech · Tanger · Agadir · Fès  
**Pipeline:** Scrapy → PostgreSQL Staging → Clean → Data Warehouse → BI + ML

---

## Architecture

```
Avito.ma
    │
    ▼
┌─────────────┐
│   SCRAPER   │  Scrapy spider — politeness delays, rotating UA
│  (Scrapy)   │  Extracts: title, price, city, area, rooms, floor...
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   STAGING   │  Raw data stored in staging.raw_listings
│ (PostgreSQL)│  Scrape logs, error handling, deduplication
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    CLEAN    │  Type conversion, outlier removal (3×IQR)
│   LAYER     │  City normalization, feature engineering
└──────┬──────┘
       │
       ├────────────────────┐
       ▼                    ▼
┌─────────────┐    ┌─────────────────┐
│  BI SCHEMA  │    │   ML SCHEMA     │
│ Star Schema │    │  One Big Table  │
│  (Power BI) │    │  (Feature Store)│
└─────────────┘    └────────┬────────┘
                            │
                    ┌───────┴────────┐
                    ▼                ▼
             ┌──────────┐    ┌──────────────┐
             │ FastAPI  │    │  Next.js App │
             │  3 ML    │    │  Dashboard   │
             │  Models  │    │              │
             └──────────┘    └──────────────┘
```

---

## Project Structure

```
avito-pipeline/
├── docker-compose.yml          # Full pipeline orchestration
├── .env                        # DB credentials
├── init/
│   └── 01_init.sql             # Schema creation (staging/clean/bi/ml)
├── scraper/                    # Scrapy spider
│   ├── Dockerfile
│   ├── requirements.txt
│   └── avito_spider/
│       ├── settings.py         # Scrapy settings + anti-bot config
│       ├── items.py
│       ├── pipelines.py        # DB + JSON pipeline
│       └── spiders/
│           └── avito_spider.py
├── staging/                    # Raw data loader
│   ├── Dockerfile
│   └── load_staging.py
├── clean/                      # Data cleaning layer
│   ├── Dockerfile
│   └── clean_data.py
├── warehouse/                  # BI + ML loader
│   ├── Dockerfile
│   └── load_warehouse.py
├── ml/                         # Machine learning
│   ├── Dockerfile
│   ├── train.py                # 3 models training
│   ├── outputs/                # Saved models + plots
│   │   ├── linear_regression.pkl
│   │   ├── logistic_regression.pkl
│   │   ├── xgboost.pkl
│   │   ├── scaler.pkl
│   │   ├── le_city.pkl
│   │   ├── le_category.pkl
│   │   ├── confusion_matrix_*.png
│   │   └── feature_importance.png
│   └── api/                    # FastAPI prediction server
│       ├── Dockerfile
│       ├── requirements.txt
│       └── main.py
├── ml_predicting_models/       # Next.js web app
│   └── app/
│       └── page.tsx
└── logs/                       # Pipeline logs per layer
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Python · Scrapy · Brotli |
| Database | PostgreSQL 15 (Docker) |
| Pipeline | Docker Compose |
| Data Processing | Pandas · NumPy · SQLAlchemy |
| Machine Learning | Scikit-learn · XGBoost · Joblib |
| API | FastAPI · Uvicorn · Pydantic |
| Frontend | Next.js 14 · TypeScript · Framer Motion |
| BI | Power BI Desktop |

---

## Pipeline Layers

### 1. Scraper
- Built with **Scrapy** — not requests/BeautifulSoup
- Targets `href` patterns matching `/fr/.+_\d+\.htm` (real ad URLs)
- Extracts price, city, area, rooms, bathrooms, floor from text nodes
- **Anti-bot measures:** Chrome user-agent, no `br` encoding, 3s delays, AutoThrottle
- `ROBOTSTXT_OBEY = False` (required — robots.txt blocks Scrapy bot)
- Writes to `staging.raw_listings` via pipeline + JSON file

### 2. Staging
- Loads JSON output into `staging.raw_listings`
- `ON CONFLICT (ad_url) DO NOTHING` — safe for re-runs
- Tracks `load_status`: `loaded` → `processed`

### 3. Clean
- Removes prices outside 100k–15M DH range
- Fills nulls with column median (rooms, bathrooms, floor, property_age)
- Normalizes city names (e.g. "casa" → "Casablanca")
- Outlier removal via **3×IQR** on price and area_m2
- Feature engineering: `price_per_m2`, `property_age`
- All values converted to plain Python types before DB insert (fixes NAType)

### 4. Warehouse
- **BI Schema** — Star Schema with fact + 3 dimension tables
- **ML Schema** — One Big Table (flat feature store)
- Full reload on each run (TRUNCATE + INSERT)

---

## Data Warehouse

### BI Schema (Star Schema)

```
fact_announcement
    ├── time_id        → dim_time (year, quarter, month, week)
    ├── localisation_id → dim_localisation (city, district)
    └── property_id    → dim_property (rooms, bathrooms, floor, year_built)
```

### ML Schema (One Big Table)

```
ml_schema.feature_store
    id, title, price, city, district, area_m2, rooms,
    bathrooms, floor, year_built, price_per_m2,
    property_age, scraped_at
```

---

## Machine Learning

Three models trained on **746 clean rows** (after price/area filtering):

### Models

| Model | Task | Metric |
|---|---|---|
| Linear Regression | Predict exact price (DH) | MAE + R² |
| Logistic Regression | Classify price category | Accuracy + F1 |
| XGBoost | Classify price category | Accuracy + F1 |

### Price Categories

| Category | Price Range |
|---|---|
| Budget | < 500,000 DH |
| Mid-range | 500,000 – 1,500,000 DH |
| Premium | 1,500,000 – 4,000,000 DH |
| Luxury | > 4,000,000 DH |

### Features Used

```
area_m2 · rooms · bathrooms · floor · property_age · price_per_m2 · city (encoded)
```

### Class Distribution

```
Premium    408  (55%)
Mid-range  144  (19%)
Luxury     114  (15%)
Budget      80  (11%)
```

### Outputs

```
ml/outputs/
├── linear_regression.pkl
├── logistic_regression.pkl
├── xgboost.pkl
├── scaler.pkl
├── le_city.pkl
├── le_category.pkl
├── linear_regression.png       # Actual vs Predicted
├── logistic_confusion.png      # Confusion matrix
├── xgb_confusion.png           # Confusion matrix
└── xgb_feature_importance.png
```

---

## FastAPI

REST API serving all 3 models on **port 8000**.

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/cities` | Available cities |
| GET | `/categories` | Price categories |
| POST | `/predict/price` | Linear Regression — exact price |
| POST | `/predict/category/logistic` | Logistic Regression — category |
| POST | `/predict/category/xgboost` | XGBoost — category |
| POST | `/predict/all` | All 3 models at once |

### Request Body

```json
{
  "area_m2": 120,
  "rooms": 3,
  "bathrooms": 2,
  "floor": 2,
  "property_age": 5,
  "city": "Casablanca",
  "price_per_m2": 12000
}
```

### Example Response — `/predict/all`

```json
{
  "linear_regression": {
    "predicted_price_dh": 1850000,
    "formatted": "1,850,000 DH"
  },
  "logistic_regression": {
    "category": "Premium",
    "confidence": "74.2%",
    "probabilities": {
      "Budget": 2.1,
      "Mid-range": 18.3,
      "Premium": 74.2,
      "Luxury": 5.4
    }
  },
  "xgboost": {
    "category": "Premium",
    "confidence": "81.5%",
    "probabilities": { ... }
  }
}
```

Swagger UI: **http://localhost:8000/docs**

---

## Web Application

Built with **Next.js 14 + TypeScript + Framer Motion**.

### Features
- Model selector (4 cards — Linear, Logistic, XGBoost, All)
- Dynamic accent color per model
- Slider-based property input with live value display
- Animated prediction results with probability bars
- API status indicator (live health check)
- "Both classifiers agree" badge when models match

### Run

```bash
cd ml_predicting_models
npm install
npm run dev
# → http://localhost:3000
```

---

## Power BI Dashboard

Connect Power BI to the PostgreSQL warehouse:

```
Server:   localhost:5432
Database: avito_db
Username: avito_user
Password: avito_pass
```

**Import tables:**
- `bi_schema.fact_announcement`
- `bi_schema.dim_localisation`
- `bi_schema.dim_time`
- `bi_schema.dim_property`

**Suggested visuals:**
- Average price by city (bar chart)
- Price per m² heatmap by district
- Listings count over time
- Price category distribution (donut)
- Area vs Price scatter plot

---

## Setup & Run

### Prerequisites
- Docker Desktop
- Node.js 18+
- Power BI Desktop (optional)

### Full Pipeline

```bash
# Clone and configure
cp .env.example .env

# Run entire pipeline (scrape → stage → clean → warehouse)
docker-compose up --build

# Check data loaded
docker exec -it avito_postgres psql -U avito_user -d avito_db -c "
SELECT 'staging' AS layer, COUNT(*) FROM staging.raw_listings
UNION ALL SELECT 'clean', COUNT(*) FROM clean.listings
UNION ALL SELECT 'ml', COUNT(*) FROM ml_schema.feature_store
UNION ALL SELECT 'bi', COUNT(*) FROM bi_schema.fact_announcement;"
```

### Train ML Models

```bash
docker-compose run --no-deps ml_train
```

### Start API

```bash
docker-compose up ml_api
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Start Web App

```bash
cd ml_predicting_models
npm install && npm run dev
# App: http://localhost:3000
```

### Keep DB running (without re-scraping)

```bash
docker-compose up db
```

---

## Compliance & Ethics

| Principle | Implementation |
|---|---|
| Data minimization | Only public listing fields scraped |
| No personal data | Names, phones, emails strictly excluded |
| Politeness | 3s+ delays, AutoThrottle, 1 concurrent request |
| Purpose limitation | Data used only for price analysis and ML |
| Storage limitation | Staging marked processed after warehouse load |
| Transparency | All scrape runs logged in `staging.scrape_logs` |

> ⚠️ This project is for educational purposes. Always verify compliance with the target website's terms of service before scraping.

---

## Database Quick Reference

```sql
-- Connect
docker exec -it avito_postgres psql -U avito_user -d avito_db

-- List schemas
\dn

-- List tables in schema
\dt bi_schema.*

-- Average price by city
SELECT l.city, ROUND(AVG(f.price_per_m2)) as avg_price_m2, COUNT(*) as listings
FROM bi_schema.fact_announcement f
JOIN bi_schema.dim_localisation l ON f.localisation_id = l.localisation_id
GROUP BY l.city ORDER BY avg_price_m2 DESC;
```

---
[Dashboard github Link](https://github.com/Anwar-saadaoui/power_bi_dashboard.git)

*Built with ❤️ — Scrapy · PostgreSQL · Docker · FastAPI · XGBoost · Next.js*

-- ============================================================
-- SCHEMAS
-- ============================================================
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS bi_schema;
CREATE SCHEMA IF NOT EXISTS ml_schema;

-- ============================================================
-- STAGING TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS staging.raw_listings (
    id               SERIAL PRIMARY KEY,
    title            TEXT,
    price_raw        TEXT,
    city_raw         TEXT,
    district_raw     TEXT,
    area_raw         TEXT,
    rooms_raw        TEXT,
    bathrooms_raw    TEXT,
    floor_raw        TEXT,
    year_built_raw   TEXT,
    ad_url           TEXT UNIQUE,
    scraped_at       TIMESTAMP DEFAULT NOW(),
    load_status      TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS staging.scrape_logs (
    id           SERIAL PRIMARY KEY,
    run_at       TIMESTAMP DEFAULT NOW(),
    pages_done   INT,
    listings_found INT,
    errors       TEXT,
    status       TEXT
);

-- ============================================================
-- CLEAN TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS clean.listings (
    id            SERIAL PRIMARY KEY,
    title         TEXT,
    price         NUMERIC(12,2),
    city          TEXT,
    district      TEXT,
    area_m2       NUMERIC(8,2),
    rooms         INT,
    bathrooms     INT,
    floor         INT,
    year_built    INT,
    ad_url        TEXT UNIQUE,
    price_per_m2  NUMERIC(12,2),
    property_age  INT,
    scraped_at    TIMESTAMP,
    cleaned_at    TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- BI SCHEMA — STAR SCHEMA
-- ============================================================
CREATE TABLE IF NOT EXISTS bi_schema.dim_time (
    time_id      SERIAL PRIMARY KEY,
    full_date    DATE,
    year         INT,
    quarter      INT,
    month        INT,
    month_name   TEXT,
    week         INT,
    day_of_week  TEXT
);

CREATE TABLE IF NOT EXISTS bi_schema.dim_localisation (
    localisation_id SERIAL PRIMARY KEY,
    city            TEXT,
    district        TEXT
);

CREATE TABLE IF NOT EXISTS bi_schema.dim_property (
    property_id  SERIAL PRIMARY KEY,
    rooms        INT,
    bathrooms    INT,
    floor        INT,
    year_built   INT,
    property_age INT
);

CREATE TABLE IF NOT EXISTS bi_schema.fact_announcement (
    fact_id         SERIAL PRIMARY KEY,
    time_id         INT REFERENCES bi_schema.dim_time(time_id),
    localisation_id INT REFERENCES bi_schema.dim_localisation(localisation_id),
    property_id     INT REFERENCES bi_schema.dim_property(property_id),
    title           TEXT,
    price           NUMERIC(12,2),
    area_m2         NUMERIC(8,2),
    price_per_m2    NUMERIC(12,2),
    ad_url          TEXT
);

CREATE INDEX IF NOT EXISTS idx_fact_time    ON bi_schema.fact_announcement(time_id);
CREATE INDEX IF NOT EXISTS idx_fact_local   ON bi_schema.fact_announcement(localisation_id);
CREATE INDEX IF NOT EXISTS idx_fact_prop    ON bi_schema.fact_announcement(property_id);

-- ============================================================
-- ML SCHEMA — ONE BIG TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_schema.feature_store (
    id            SERIAL PRIMARY KEY,
    title         TEXT,
    price         NUMERIC(12,2),
    city          TEXT,
    district      TEXT,
    area_m2       NUMERIC(8,2),
    rooms         INT,
    bathrooms     INT,
    floor         INT,
    year_built    INT,
    price_per_m2  NUMERIC(12,2),
    property_age  INT,
    scraped_at    TIMESTAMP
);
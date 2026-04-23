import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
import pandas as pd
import numpy as np

load_dotenv()

os.makedirs("/app/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CLEAN] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/clean.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

CURRENT_YEAR = datetime.utcnow().year

CITY_MAP = {
    "casa": "Casablanca", "casablanca": "Casablanca",
    "rabat": "Rabat", "marrakech": "Marrakech", "marrakesh": "Marrakech",
    "fes": "Fès", "fès": "Fès", "tanger": "Tanger", "tangier": "Tanger",
    "agadir": "Agadir", "meknes": "Meknès", "meknès": "Meknès",
    "oujda": "Oujda", "kenitra": "Kénitra", "kénitra": "Kénitra",
    "tetouan": "Tétouan", "tétouan": "Tétouan", "sale": "Salé", "salé": "Salé",
    "mohammedia": "Mohammedia", "el jadida": "El Jadida", "safi": "Safi",
    "beni mellal": "Beni Mellal", "settat": "Settat", "nador": "Nador",
    "khouribga": "Khouribga",
}


def to_int(val):
    try:
        if val is None:
            return None
        s = str(val)
        if s in ("nan", "<NA>", "None", "NaT", ""):
            return None
        return int(float(s))
    except:
        return None


def to_float(val):
    try:
        if val is None:
            return None
        s = str(val)
        if s in ("nan", "<NA>", "None", "NaT", ""):
            return None
        return float(s)
    except:
        return None


def normalize_city(raw):
    if not raw or str(raw).strip().lower() in ("none", "nan", ""):
        return None
    key = str(raw).lower().strip()
    for k, v in CITY_MAP.items():
        if k in key:
            return v
    return str(raw).strip().title()


def extract_number(text):
    if not text or str(text).strip().lower() in ("none", "nan", ""):
        return None
    nums = re.findall(r'[\d]+', str(text).replace('\u00a0', '').replace(' ', ''))
    for n in nums:
        try:
            return float(n)
        except ValueError:
            continue
    return None


def remove_outliers_iqr(df, col):
    if col not in df.columns or df[col].dropna().empty:
        return df
    q1  = df[col].quantile(0.25)
    q3  = df[col].quantile(0.75)
    iqr = q3 - q1
    lo  = q1 - 3 * iqr
    hi  = q3 + 3 * iqr
    before = len(df)
    df = df[(df[col].isna()) | ((df[col] >= lo) & (df[col] <= hi))]
    log.info(f"[OUTLIERS] {col}: {before} → {len(df)}")
    return df


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    log.info("=== CLEANING START ===")
    conn = get_db()

    db_url = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    df = pd.read_sql(
        "SELECT * FROM staging.raw_listings WHERE load_status = 'loaded'",
        con=db_url,
    )
    log.info(f"Loaded {len(df)} raw rows")

    if df.empty:
        log.info("Nothing to clean.")
        conn.close()
        return

    # ── Numeric extraction ────────────────────────────────────
    df["price"]      = df["price_raw"].apply(extract_number)
    df["area_m2"]    = df["area_raw"].apply(extract_number)
    df["rooms"]      = df["rooms_raw"].apply(extract_number)
    df["bathrooms"]  = df["bathrooms_raw"].apply(extract_number)
    df["floor"]      = df["floor_raw"].apply(extract_number)
    df["year_built"] = df["year_built_raw"].apply(extract_number)

    # Keep as float64 — never use Int64 (causes NAType)
    for col in ["price", "area_m2", "rooms", "bathrooms", "floor", "year_built"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── City normalization ────────────────────────────────────
    df["city"] = df["city_raw"].apply(normalize_city)
    df["district"] = df["district_raw"].apply(
        lambda x: str(x).strip().title()
        if x and str(x).lower() not in ("none", "nan", "") else None
    )

    # ── Dedup ─────────────────────────────────────────────────
    df = df.drop_duplicates(subset=["ad_url"])
    log.info(f"After dedup: {len(df)}")

    # ── Price filter ──────────────────────────────────────────
    df = df.dropna(subset=["price"])
    df = df[df["price"] > 0]
    log.info(f"After price filter: {len(df)}")

    # ── Outlier removal ───────────────────────────────────────
    df = remove_outliers_iqr(df, "price")
    df = remove_outliers_iqr(df, "area_m2")

    # ── Feature engineering ───────────────────────────────────
    df["price_per_m2"] = np.where(
        df["area_m2"].notna() & (df["area_m2"] > 0),
        (df["price"] / df["area_m2"]).round(2),
        np.nan,
    )
    df["property_age"] = np.where(
        df["year_built"].notna() & (df["year_built"] > 1900),
        CURRENT_YEAR - df["year_built"],
        np.nan,
    )

    log.info(f"Final clean dataset: {len(df)} rows")

    # ── Insert ────────────────────────────────────────────────
    cur = conn.cursor()
    inserted = 0

    for _, row in df.iterrows():
        try:
            cur.execute(
                """
                INSERT INTO clean.listings
                  (title, price, city, district, area_m2, rooms, bathrooms,
                   floor, year_built, ad_url, price_per_m2, property_age, scraped_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (ad_url) DO UPDATE SET
                  price        = EXCLUDED.price,
                  price_per_m2 = EXCLUDED.price_per_m2,
                  cleaned_at   = NOW()
                """,
                (
                    str(row["title"])[:500] if row.get("title") else None,
                    to_float(row["price"]),
                    row.get("city"),
                    row.get("district"),
                    to_float(row["area_m2"]),
                    to_int(row["rooms"]),
                    to_int(row["bathrooms"]),
                    to_int(row["floor"]),
                    to_int(row["year_built"]),
                    str(row["ad_url"]) if row.get("ad_url") else None,
                    to_float(row["price_per_m2"]),
                    to_int(row["property_age"]),
                    row.get("scraped_at"),
                ),
            )
            inserted += 1
        except Exception as e:
            log.warning(f"Insert error: {e}")
            conn.rollback()
            continue

    cur.execute(
        "UPDATE staging.raw_listings SET load_status='processed' WHERE load_status='loaded'"
    )
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"Inserted: {inserted} rows")
    log.info("=== CLEANING DONE ===")


if __name__ == "__main__":
    main()
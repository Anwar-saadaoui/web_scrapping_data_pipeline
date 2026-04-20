import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
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

# ── City normalization map ────────────────────────────────────
CITY_MAP = {
    "casa":           "Casablanca",
    "casablanca":     "Casablanca",
    "rabat":          "Rabat",
    "marrakech":      "Marrakech",
    "marrakesh":      "Marrakech",
    "fes":            "Fès",
    "fès":            "Fès",
    "tanger":         "Tanger",
    "tangier":        "Tanger",
    "agadir":         "Agadir",
    "meknes":         "Meknès",
    "meknès":         "Meknès",
    "oujda":          "Oujda",
    "kenitra":        "Kénitra",
    "kénitra":        "Kénitra",
    "tetouan":        "Tétouan",
    "tétouan":        "Tétouan",
    "sale":           "Salé",
    "salé":           "Salé",
    "mohammedia":     "Mohammedia",
    "el jadida":      "El Jadida",
    "safi":           "Safi",
    "beni mellal":    "Beni Mellal",
    "béni mellal":    "Beni Mellal",
    "settat":         "Settat",
    "nador":          "Nador",
    "khouribga":      "Khouribga",
}


def normalize_city(raw: str) -> str:
    if not raw:
        return None
    key = raw.lower().strip()
    for k, v in CITY_MAP.items():
        if k in key:
            return v
    return raw.strip().title()


def extract_number(text: str) -> float | None:
    if not text:
        return None
    nums = re.findall(r"[\d\s]+(?:[.,]\d+)?", text)
    for n in nums:
        clean = n.replace(" ", "").replace(",", ".")
        try:
            return float(clean)
        except ValueError:
            continue
    return None


def remove_outliers_iqr(df: pd.DataFrame, col: str) -> pd.DataFrame:
    q1 = df[col].quantile(0.25)
    q3 = df[col].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 3 * iqr
    upper = q3 + 3 * iqr
    before = len(df)
    df = df[(df[col].isna()) | ((df[col] >= lower) & (df[col] <= upper))]
    log.info(f"Outlier removal on '{col}': {before} → {len(df)} rows")
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
    log.info("=== Cleaning started ===")
    conn = get_db()

    df = pd.read_sql(
        "SELECT * FROM staging.raw_listings WHERE load_status = 'loaded'",
        conn,
    )
    log.info(f"Fetched {len(df)} rows from staging")

    if df.empty:
        log.info("Nothing to clean.")
        conn.close()
        return

    # ── Numeric extraction ────────────────────────────────────
    df["price"]     = df["price_raw"].apply(extract_number)
    df["area_m2"]   = df["area_raw"].apply(extract_number)
    df["rooms"]     = df["rooms_raw"].apply(extract_number)
    df["bathrooms"] = df["bathrooms_raw"].apply(extract_number)
    df["floor"]     = df["floor_raw"].apply(extract_number)
    df["year_built"]= df["year_built_raw"].apply(extract_number)

    # ── Type conversion ───────────────────────────────────────
    for col in ["rooms", "bathrooms", "floor", "year_built"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # ── City normalization ────────────────────────────────────
    df["city"]     = df["city_raw"].apply(normalize_city)
    df["district"] = df["district_raw"].apply(
        lambda x: x.strip().title() if x else None
    )

    # ── Remove duplicates ─────────────────────────────────────
    df = df.drop_duplicates(subset=["ad_url"])

    # ── Drop rows without price or area ──────────────────────
    df = df.dropna(subset=["price"])

    # ── Outlier removal (price, area) ─────────────────────────
    df = remove_outliers_iqr(df, "price")
    df = remove_outliers_iqr(df.dropna(subset=["area_m2"]), "area_m2") if "area_m2" in df else df

    # ── Feature engineering ───────────────────────────────────
    df["price_per_m2"] = np.where(
        df["area_m2"].notna() & (df["area_m2"] > 0),
        (df["price"] / df["area_m2"]).round(2),
        None,
    )
    df["property_age"] = np.where(
        df["year_built"].notna() & (df["year_built"] > 1900),
        CURRENT_YEAR - df["year_built"],
        None,
    )

    log.info(f"Clean rows ready: {len(df)}")

    # ── Load into clean schema ────────────────────────────────
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
                    row.get("title"),
                    row.get("price") if pd.notna(row.get("price")) else None,
                    row.get("city"),
                    row.get("district"),
                    row.get("area_m2") if pd.notna(row.get("area_m2")) else None,
                    int(row["rooms"]) if pd.notna(row.get("rooms")) else None,
                    int(row["bathrooms"]) if pd.notna(row.get("bathrooms")) else None,
                    int(row["floor"]) if pd.notna(row.get("floor")) else None,
                    int(row["year_built"]) if pd.notna(row.get("year_built")) else None,
                    row.get("ad_url"),
                    row.get("price_per_m2") if pd.notna(row.get("price_per_m2")) else None,
                    int(row["property_age"]) if pd.notna(row.get("property_age")) else None,
                    row.get("scraped_at"),
                ),
            )
            inserted += 1
        except Exception as e:
            log.warning(f"Insert error: {e}")
            conn.rollback()

    # Mark staging rows as processed
    cur.execute("UPDATE staging.raw_listings SET load_status = 'processed' WHERE load_status = 'loaded'")
    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Inserted/updated {inserted} rows in clean.listings")
    log.info("=== Cleaning done ===")


if __name__ == "__main__":
    main()
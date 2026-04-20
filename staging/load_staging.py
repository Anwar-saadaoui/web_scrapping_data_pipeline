import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

os.makedirs("/app/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [STAGING] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/staging.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

RAW_FILE = "/data/scraped_raw.json"


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    log.info("=== Staging load started ===")

    if not os.path.exists(RAW_FILE):
        log.error(f"Raw file not found: {RAW_FILE}")
        raise FileNotFoundError(RAW_FILE)

    with open(RAW_FILE, encoding="utf-8") as f:
        records = json.load(f)

    log.info(f"Loaded {len(records)} records from JSON")

    conn = get_db()
    cur  = conn.cursor()

    inserted = 0
    skipped  = 0

    for r in records:
        try:
            cur.execute(
                """
                INSERT INTO staging.raw_listings
                  (title, price_raw, city_raw, district_raw, area_raw,
                   rooms_raw, bathrooms_raw, floor_raw, year_built_raw,
                   ad_url, scraped_at, load_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'loaded')
                ON CONFLICT (ad_url) DO NOTHING
                """,
                (
                    r.get("title"),
                    r.get("price_raw"),
                    r.get("city_raw"),
                    r.get("district_raw"),
                    r.get("area_raw"),
                    r.get("rooms_raw"),
                    r.get("bathrooms_raw"),
                    r.get("floor_raw"),
                    r.get("year_built_raw"),
                    r.get("ad_url"),
                    r.get("scraped_at"),
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            log.warning(f"Row error: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Inserted: {inserted} | Skipped (dup): {skipped}")
    log.info("=== Staging load done ===")


if __name__ == "__main__":
    main()
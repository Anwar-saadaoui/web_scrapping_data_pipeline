import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
import pandas as pd

load_dotenv()

os.makedirs("/app/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WAREHOUSE] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/warehouse.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def upsert_dim_time(cur, date_val):
    if date_val is None:
        return None
    d = date_val if hasattr(date_val, "year") else datetime.fromisoformat(str(date_val))
    cur.execute(
        """
        INSERT INTO bi_schema.dim_time
          (full_date, year, quarter, month, month_name, week, day_of_week)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        RETURNING time_id
        """,
        (
            d.date(),
            d.year,
            (d.month - 1) // 3 + 1,
            d.month,
            d.strftime("%B"),
            d.isocalendar()[1],
            d.strftime("%A"),
        ),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # Already existed — fetch id
    cur.execute("SELECT time_id FROM bi_schema.dim_time WHERE full_date = %s", (d.date(),))
    row = cur.fetchone()
    return row[0] if row else None


def upsert_dim_localisation(cur, city, district):
    cur.execute(
        """
        INSERT INTO bi_schema.dim_localisation (city, district)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        RETURNING localisation_id
        """,
        (city, district),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "SELECT localisation_id FROM bi_schema.dim_localisation WHERE city=%s AND district IS NOT DISTINCT FROM %s",
        (city, district),
    )
    row = cur.fetchone()
    return row[0] if row else None


def upsert_dim_property(cur, rooms, bathrooms, floor, year_built, property_age):
    cur.execute(
        """
        INSERT INTO bi_schema.dim_property
          (rooms, bathrooms, floor, year_built, property_age)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        RETURNING property_id
        """,
        (rooms, bathrooms, floor, year_built, property_age),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """SELECT property_id FROM bi_schema.dim_property
           WHERE rooms IS NOT DISTINCT FROM %s
             AND bathrooms IS NOT DISTINCT FROM %s
             AND floor IS NOT DISTINCT FROM %s
             AND year_built IS NOT DISTINCT FROM %s""",
        (rooms, bathrooms, floor, year_built),
    )
    row = cur.fetchone()
    return row[0] if row else None


def main():
    log.info("=== Warehouse load started ===")
    conn = get_db()

    df = pd.read_sql("SELECT * FROM clean.listings", conn)
    log.info(f"Loaded {len(df)} rows from clean.listings")

    if df.empty:
        log.info("No data to load into warehouse.")
        conn.close()
        return

    cur = conn.cursor()

    # ── Truncate facts (full reload) ──────────────────────────
    cur.execute("TRUNCATE TABLE bi_schema.fact_announcement RESTART IDENTITY CASCADE")
    cur.execute("TRUNCATE TABLE ml_schema.feature_store RESTART IDENTITY CASCADE")

    fact_rows  = 0
    ml_rows    = 0

    for _, row in df.iterrows():
        try:
            scraped_at = row.get("scraped_at")

            # Dimensions
            time_id         = upsert_dim_time(cur, scraped_at)
            localisation_id = upsert_dim_localisation(cur, row.get("city"), row.get("district"))
            property_id     = upsert_dim_property(
                cur,
                int(row["rooms"])       if pd.notna(row.get("rooms"))       else None,
                int(row["bathrooms"])   if pd.notna(row.get("bathrooms"))   else None,
                int(row["floor"])       if pd.notna(row.get("floor"))       else None,
                int(row["year_built"])  if pd.notna(row.get("year_built"))  else None,
                int(row["property_age"])if pd.notna(row.get("property_age"))else None,
            )

            # Fact
            cur.execute(
                """
                INSERT INTO bi_schema.fact_announcement
                  (time_id, localisation_id, property_id, title,
                   price, area_m2, price_per_m2, ad_url)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    time_id,
                    localisation_id,
                    property_id,
                    row.get("title"),
                    float(row["price"])       if pd.notna(row.get("price"))       else None,
                    float(row["area_m2"])     if pd.notna(row.get("area_m2"))     else None,
                    float(row["price_per_m2"])if pd.notna(row.get("price_per_m2"))else None,
                    row.get("ad_url"),
                ),
            )
            fact_rows += 1

            # ML OBT
            cur.execute(
                """
                INSERT INTO ml_schema.feature_store
                  (title, price, city, district, area_m2, rooms, bathrooms,
                   floor, year_built, price_per_m2, property_age, scraped_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    row.get("title"),
                    float(row["price"])       if pd.notna(row.get("price"))       else None,
                    row.get("city"),
                    row.get("district"),
                    float(row["area_m2"])     if pd.notna(row.get("area_m2"))     else None,
                    int(row["rooms"])         if pd.notna(row.get("rooms"))       else None,
                    int(row["bathrooms"])     if pd.notna(row.get("bathrooms"))   else None,
                    int(row["floor"])         if pd.notna(row.get("floor"))       else None,
                    int(row["year_built"])    if pd.notna(row.get("year_built"))  else None,
                    float(row["price_per_m2"])if pd.notna(row.get("price_per_m2"))else None,
                    int(row["property_age"])  if pd.notna(row.get("property_age"))else None,
                    scraped_at,
                ),
            )
            ml_rows += 1

        except Exception as e:
            log.warning(f"Row error: {e}")
            conn.rollback()

    conn.commit()

    # ── Data validation ───────────────────────────────────────
    for table, schema in [
        ("fact_announcement", "bi_schema"),
        ("dim_localisation",  "bi_schema"),
        ("dim_property",      "bi_schema"),
        ("dim_time",          "bi_schema"),
        ("feature_store",     "ml_schema"),
    ]:
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        count = cur.fetchone()[0]
        log.info(f"  {schema}.{table}: {count} rows")

    cur.close()
    conn.close()

    log.info(f"Fact rows: {fact_rows} | ML rows: {ml_rows}")
    log.info("=== Warehouse load done ===")


if __name__ == "__main__":
    main()
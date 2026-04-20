import os
import json
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import psycopg2

load_dotenv()

# ── Logging ────────────────────────────────────────────────
os.makedirs("/app/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCRAPER] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/scraper.log"),
        logging.StreamHandler(),
    ],
)

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
URL = "https://www.avito.ma/fr/maroc/appartements-_-villas/%C3%A0_vendre"
OUTPUT = "/app/data/scraped_raw.json"

# ── DB ────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

# ── Scraper ───────────────────────────────────────────────
def scrape():
    log.info("=== PLAYWRIGHT SCRAPER STARTED ===")

    all_data = []
    scraped_at = datetime.utcnow().isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        log.info(f"Opening: {URL}")
        page.goto(URL, timeout=60000)

        # wait for JS to load listings
        page.wait_for_timeout(5000)

        # scroll to load more results
        for _ in range(3):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(2000)

        # ── extract cards ───────────────────────────────
        cards = page.query_selector_all("article, div")

        log.info(f"Raw elements found: {len(cards)}")

        for c in cards:
            try:
                text = c.inner_text().strip()

                if not text:
                    continue

                # basic filter (avoid nav/footer junk)
                if len(text) < 50:
                    continue

                all_data.append({
                    "raw_text": text[:300],
                    "scraped_at": scraped_at
                })

            except:
                continue

        browser.close()

    log.info(f"TOTAL SCRAPED: {len(all_data)}")

    # ── Save JSON ─────────────────────────────────────
    os.makedirs("/app/data", exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    log.info(f"Saved → {OUTPUT}")

    # ── DB LOG ───────────────────────────────────────
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO staging.scrape_logs
            (pages_done, listings_found, errors, status)
            VALUES (%s, %s, %s, %s)
            """,
            (1, len(all_data), None, "ok"),
        )

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        log.error(f"DB error: {e}")

    log.info("=== DONE ===")


if __name__ == "__main__":
    scrape()
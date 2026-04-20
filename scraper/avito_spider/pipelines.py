import json
import logging
import psycopg2
from datetime import datetime, timezone
from itemadapter import ItemAdapter

log = logging.getLogger(__name__)


class PostgresPipeline:
    """Write every item directly into staging.raw_listings."""

    def open_spider(self, spider):
        cfg = spider.settings
        self.conn = psycopg2.connect(
            host=cfg.get("DB_HOST"),
            port=cfg.get("DB_PORT"),
            dbname=cfg.get("DB_NAME"),
            user=cfg.get("DB_USER"),
            password=cfg.get("DB_PASSWORD"),
        )
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        self.inserted = 0
        self.skipped  = 0
        log.info("PostgresPipeline: connected to DB")

    def close_spider(self, spider):
        # Write scrape log
        try:
            self.cur.execute(
                """INSERT INTO staging.scrape_logs
                   (pages_done, listings_found, errors, status)
                   VALUES (%s, %s, %s, %s)""",
                (
                    getattr(spider, "pages_crawled", 0),
                    self.inserted,
                    None,
                    "ok",
                ),
            )
            self.conn.commit()
        except Exception as e:
            log.error(f"Could not write scrape log: {e}")
        self.cur.close()
        self.conn.close()
        log.info(f"PostgresPipeline closed — inserted={self.inserted} skipped={self.skipped}")

    def process_item(self, item, spider):
        a = ItemAdapter(item)
        try:
            self.cur.execute(
                """
                INSERT INTO staging.raw_listings
                  (title, price_raw, city_raw, district_raw, area_raw,
                   rooms_raw, bathrooms_raw, floor_raw, year_built_raw,
                   ad_url, scraped_at, load_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'loaded')
                ON CONFLICT (ad_url) DO NOTHING
                """,
                (
                    a.get("title"),
                    a.get("price_raw"),
                    a.get("city_raw"),
                    a.get("district_raw"),
                    a.get("area_raw"),
                    a.get("rooms_raw"),
                    a.get("bathrooms_raw"),
                    a.get("floor_raw"),
                    a.get("year_built_raw"),
                    a.get("ad_url"),
                    a.get("scraped_at"),
                ),
            )
            if self.cur.rowcount > 0:
                self.inserted += 1
            else:
                self.skipped += 1
            self.conn.commit()
        except Exception as e:
            log.warning(f"DB insert error: {e}")
            self.conn.rollback()
        log.info(f"INSERTING: {item['title']}")
        return item


class JsonFilePipeline:
    """Also dump everything to a JSON file (for the staging service)."""

    def open_spider(self, spider):
        path = spider.settings.get("FEED_JSON_PATH", "/app/scraped_raw.json")
        self.file   = open(path, "w", encoding="utf-8")
        self.items  = []
        log.info(f"JsonFilePipeline: writing to {path}")

    def close_spider(self, spider):
        json.dump(self.items, self.file, ensure_ascii=False, indent=2)
        self.file.close()
        log.info(f"JsonFilePipeline: wrote {len(self.items)} items")

    def process_item(self, item, spider):
        self.items.append(dict(item))
        return item
import os
from dotenv import load_dotenv
load_dotenv()

BOT_NAME = "avito_spider"
SPIDER_MODULES = ["avito_spider.spiders"]
NEWSPIDER_MODULE = "avito_spider.spiders"

ROBOTSTXT_OBEY = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 12
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

DOWNLOADER_MIDDLEWARES = {}

# ── KEY FIX: remove br encoding — Scrapy can't decompress Brotli ──
DEFAULT_REQUEST_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",   # NO br — causes binary garbage
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
}

ITEM_PIPELINES = {
    "avito_spider.pipelines.PostgresPipeline": 300,
    "avito_spider.pipelines.JsonFilePipeline": 400,
}

DB_HOST     = os.getenv("DB_HOST", "db")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "avito_db")
DB_USER     = os.getenv("DB_USER", "avito_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "avito_pass")

FEED_JSON_PATH = "/app/output/scraped_raw.json"

RETRY_ENABLED = True
RETRY_TIMES = 4
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

HTTPCACHE_ENABLED = False
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
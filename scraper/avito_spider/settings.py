import os
from dotenv import load_dotenv
load_dotenv()

BOT_NAME = "avito_spider"
SPIDER_MODULES = ["avito_spider.spiders"]
NEWSPIDER_MODULE = "avito_spider.spiders"

# ── Politeness ────────────────────────────────────────────────
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True          # 1.5× to 3× DOWNLOAD_DELAY
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# ── Rotating user-agents ──────────────────────────────────────
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy_user_agents.middlewares.RandomUserAgentMiddleware": 400,
}

# ── Default headers ───────────────────────────────────────────
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# ── Pipelines ─────────────────────────────────────────────────
ITEM_PIPELINES = {
    "avito_spider.pipelines.PostgresPipeline": 300,
    "avito_spider.pipelines.JsonFilePipeline": 400,
}

# ── DB connection passed to pipeline ─────────────────────────
DB_HOST     = os.getenv("DB_HOST", "db")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "avito_db")
DB_USER     = os.getenv("DB_USER", "avito_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "avito_pass")

# ── Output file ───────────────────────────────────────────────
FEED_JSON_PATH = "/app/output/scraped_raw.json"

# ── Retry on failure ──────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# ── Cache (speeds up re-runs during dev) ─────────────────────
HTTPCACHE_ENABLED = False

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
import re
import logging
import scrapy
from datetime import datetime, timezone
from avito_spider.items import ListingItem

log = logging.getLogger(__name__)

CITY_URLS = [
    "https://www.avito.ma/fr/casablanca/appartements-%C3%A0_vendre",
    "https://www.avito.ma/fr/rabat/appartements-%C3%A0_vendre",
    "https://www.avito.ma/fr/marrakech/appartements-%C3%A0_vendre",
    "https://www.avito.ma/fr/tanger/appartements-%C3%A0_vendre",
    "https://www.avito.ma/fr/agadir/appartements-%C3%A0_vendre",
    "https://www.avito.ma/fr/fes/appartements-%C3%A0_vendre",
]
MAX_PAGES_PER_CITY = 5

# Matches real ad URLs:  /fr/district/appartements/Title_12345678.htm
AD_URL_RE = re.compile(r'/fr/[^/]+/appartements/.+_\d+\.htm$')


class AvitoSpider(scrapy.Spider):
    name            = "avito"
    allowed_domains = ["avito.ma"]
    pages_crawled   = 0
    custom_settings = {"FEEDS": {}}

    def start_requests(self):
        for url in CITY_URLS:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={"page": 1, "base_url": url},
                dont_filter=True,
            )

    # ──────────────────────────────────────────────────────────
    def parse(self, response):
        self.pages_crawled += 1
        page     = response.meta["page"]
        base_url = response.meta["base_url"]

        log.info(f"[page {page}] {response.url} — HTTP {response.status} — {len(response.text)} chars")

        scraped_at = datetime.now(timezone.utc).isoformat()

        # ── Find every <a> that links to an individual ad ─────
        # Real ad href looks like:
        #   /fr/ain_chock/appartements/A_vendre_un_joli_57502425.htm
        ad_anchors = [
            a for a in response.css("a[href]")
            if AD_URL_RE.search(a.attrib["href"])
        ]

        log.info(f"  Ad anchors found: {len(ad_anchors)}")

        if not ad_anchors:
            log.warning("  Zero anchors — dumping 2000 chars of HTML for debug:")
            log.warning(response.text[:2000])

        seen = set()
        for anchor in ad_anchors:
            href = anchor.attrib["href"]
            if href in seen:
                continue
            seen.add(href)

            full_url = "https://www.avito.ma" + href if not href.startswith("http") else href

            # Skip immoneuf.avito.ma links
            if "immoneuf" in full_url:
                continue

            item = self._parse_anchor(anchor, full_url, scraped_at)
            if item:
                yield item

        # ── Pagination ────────────────────────────────────────
        if page < MAX_PAGES_PER_CITY:
            next_page = page + 1
            clean = re.sub(r'[?&]o=\d+', '', base_url).rstrip("&?")
            sep   = "&" if "?" in clean else "?"
            yield scrapy.Request(
                f"{clean}{sep}o={next_page}",
                callback=self.parse,
                meta={"page": next_page, "base_url": base_url},
                dont_filter=True,
            )

    # ──────────────────────────────────────────────────────────
    def _parse_anchor(self, anchor, full_url: str, scraped_at: str):
        """
        Each listing <a> contains ALL data we need as text nodes.
        Real example from the fetched HTML:

          Appartements dans Casablanca, Aïn Chock
          A vendre un joli appartement avec terrasse
          2 chambre(s)  2 sdb(s)  117 m²  Étage 0
          1 650 000 DH  9 171 DH / mois
        """
        texts = [t.strip() for t in anchor.css("::text").getall() if t.strip()]
        full  = " ".join(texts)

        if not texts:
            return None

        # ── Location: "Appartements dans City, District" ──────
        # Always appears as the FIRST meaningful text in the anchor
        city_raw, district_raw = None, None
        loc_match = re.search(
            r'(?:Appartements?\s+dans\s+|Ventes?\s+dans\s+)'
            r'([^,\n]+?)(?:,\s*(.+?))?(?:\s{2,}|$)',
            full, re.IGNORECASE
        )
        if loc_match:
            city_raw     = loc_match.group(1).strip()
            district_raw = loc_match.group(2).strip() if loc_match.group(2) else None
        else:
            # Fallback: find known city name in texts
            for t in texts:
                m = re.search(
                    r'\b(Casablanca|Rabat|Marrakech|Tanger|Agadir|'
                    r'Fès|Fes|Meknès|Meknes|Oujda|Kénitra|Kenitra|'
                    r'Tétouan|Tetouan|Salé|Sale|Mohammedia|El Jadida|'
                    r'Safi|Beni Mellal|Settat|Nador|Khouribga)\b',
                    t, re.IGNORECASE
                )
                if m:
                    city_raw = m.group(1)
                    rest = t[m.end():].strip().lstrip(",").strip()
                    district_raw = rest if rest else None
                    break

        # ── Title ─────────────────────────────────────────────
        # Title is a text node that is NOT location, NOT price, NOT features
        title = None
        garbage_re = re.compile(
            r'chambre|sdb|m²|étage|DH|MAD|mois|Appartements?\s+dans|'
            r'Ventes?\s+dans|Premium|Vérifié|Visiter|il y a|immoneuf',
            re.IGNORECASE
        )
        for t in texts:
            if not garbage_re.search(t) and len(t) > 8:
                title = t[:500]
                break

        if not title:
            # Use last part of URL as title
            title = full_url.split("/")[-1].replace("_", " ").replace(".htm", "")[:500]

        # ── Price: "1 650 000 DH" ─────────────────────────────
        price_match = re.search(r'([\d\s\u00a0]+)\s*DH', full)
        if not price_match:
            return None   # no price = not a real listing
        price_raw = price_match.group(0).strip()

        # ── Area: "117 m²" ────────────────────────────────────
        area_match = re.search(r'(\d[\d\s]*)\s*m²', full)
        area_raw   = area_match.group(0).strip() if area_match else None

        # ── Rooms: "2 chambre(s)" ─────────────────────────────
        rooms_match = re.search(r'(\d+)\s*chambre', full, re.IGNORECASE)
        rooms_raw   = rooms_match.group(0).strip() if rooms_match else None

        # ── Bathrooms: "2 sdb(s)" ─────────────────────────────
        bath_match    = re.search(r'(\d+)\s*sdb', full, re.IGNORECASE)
        bathrooms_raw = bath_match.group(0).strip() if bath_match else None

        # ── Floor: "Étage 4" ──────────────────────────────────
        floor_match = re.search(r'[EÉ]tage\s*(\d+)', full, re.IGNORECASE)
        floor_raw   = floor_match.group(0).strip() if floor_match else None

        # ── Year built: not on listing cards, will be None ────
        year_built_raw = None

        log.debug(
            f"  ITEM title={title!r} price={price_raw!r} "
            f"city={city_raw!r} area={area_raw!r} rooms={rooms_raw!r}"
        )

        return ListingItem(
            title          = title,
            price_raw      = price_raw,
            city_raw       = city_raw,
            district_raw   = district_raw,
            area_raw       = area_raw,
            rooms_raw      = rooms_raw,
            bathrooms_raw  = bathrooms_raw,
            floor_raw      = floor_raw,
            year_built_raw = year_built_raw,
            ad_url         = full_url,
            scraped_at     = scraped_at,
        )
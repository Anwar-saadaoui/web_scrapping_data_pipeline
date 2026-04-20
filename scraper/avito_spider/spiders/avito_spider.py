import re
import logging
import scrapy
from datetime import datetime, timezone
from avito_spider.items import ListingItem

log = logging.getLogger(__name__)

START_URL = "https://www.avito.ma/fr/maroc/appartements-_-villas/%C3%A0_vendre"
MAX_PAGES = 20


class AvitoSpider(scrapy.Spider):
    name            = "avito"
    allowed_domains = ["avito.ma"]
    start_urls      = [START_URL]
    pages_crawled   = 0

    custom_settings = {"FEEDS": {}}

    def parse(self, response):
        self.pages_crawled += 1
        log.info(f"Parsing page {self.pages_crawled}: {response.url}")

        # ── Strategy: find all links that point to individual ad pages ──
        # Avito individual ad URLs look like:
        #   /fr/maroc/appartements/titre-de-annonce_123456.htm
        # They always end in _<digits>.htm or similar
        # We find all <a> whose href matches this pattern, then walk UP
        # to the card container.

        ad_links = response.xpath(
            '//a[re:test(@href, "/fr/maroc/.+_\\d+\\.htm")]',
            namespaces={"re": "http://exslt.org/regular-expressions"}
        )

        log.info(f"  Ad links found: {len(ad_links)}")

        if not ad_links:
            log.warning("No ad links found — dumping first 3000 chars:")
            log.warning(response.text[:3000])
            return

        scraped_at = datetime.now(timezone.utc).isoformat()
        seen_urls  = set()

        for link in ad_links:
            href = link.attrib.get("href", "")
            if not href.startswith("http"):
                href = "https://www.avito.ma" + href

            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Walk up to the card container (parent or grandparent of the <a>)
            # We try: the <a> itself, its parent, grandparent — whichever has price info
            card = link.xpath(
                'ancestor::*[.//span[contains(text(),"DH") or contains(text(),"MAD")]][1]'
            )
            if not card:
                card = link  # fallback: parse from the <a> itself

            item = self._parse_card(card, href, scraped_at)
            if item:
                yield item

        # ── Pagination ────────────────────────────────────────────────
        if self.pages_crawled < MAX_PAGES:
            next_url = self._next_page(response)
            if next_url and next_url not in (response.url,):
                log.info(f"  → Next: {next_url}")
                yield response.follow(next_url, callback=self.parse)

    # ─────────────────────────────────────────────────────────────────
    def _parse_card(self, card, href: str, scraped_at: str):

        # --- Title: prefer the <a> title attr or the heading text ----
        title = (
            card.xpath('.//h2/text()').get()
            or card.xpath('.//h3/text()').get()
            or card.xpath('.//a/@title').get()
            or card.xpath(
                './/p[contains(@class,"title") or contains(@class,"Title")]'
                '/text()'
            ).get()
            or card.xpath(
                './/*[contains(@class,"title") or contains(@class,"Title")]'
                '//text()'
            ).get()
        )
        if not title:
            return None
        title = title.strip()[:500]

        # Skip footer / nav garbage
        garbage_keywords = [
            "moteur.ma", "avito group", "cookies", "newsletter",
            "télécharger", "download", "facebook", "instagram",
            "conditions", "contact", "aide", "help", "emploi"
        ]
        if any(kw in title.lower() for kw in garbage_keywords):
            return None

        # --- Price -------------------------------------------------------
        # Avito price pattern: "850 000 DH" — number and unit often split
        # across sibling spans. Collect ALL text inside the card and find it.
        all_texts = card.xpath('.//text()').getall()
        all_texts = [t.strip() for t in all_texts if t.strip()]
        full_text = " ".join(all_texts)

        # Match "1 200 000 DH" or "850000 MAD" or "1,200,000 DH"
        price_match = re.search(
            r'([\d\s\u00a0,\.]{2,})\s*(DH|MAD|dh|mad)', full_text
        )
        price_raw = price_match.group(0).strip() if price_match else None

        if not price_raw:
            return None

        # --- Location ----------------------------------------------------
        # Try explicit location elements first
        location_raw = (
            card.xpath(
                './/*[contains(@class,"location") or contains(@class,"Location")'
                '  or contains(@class,"city")     or contains(@class,"City")'
                '  or contains(@class,"region")   or contains(@class,"address")]'
                '//text()'
            ).getall()
        )

        # Fallback: look for text that contains a known Moroccan city name
        if not location_raw:
            moroccan_cities = [
                "Casablanca","Rabat","Marrakech","Fès","Tanger","Agadir",
                "Meknès","Oujda","Kénitra","Tétouan","Salé","Mohammedia",
                "El Jadida","Safi","Beni Mellal","Settat","Nador","Khouribga",
                "Kenitra","Meknes","Fes","Casa"
            ]
            pattern = "|".join(moroccan_cities)
            for t in all_texts:
                if re.search(pattern, t, re.IGNORECASE) and len(t) < 80:
                    location_raw = [t]
                    break

        location_str = " ".join(t.strip() for t in location_raw if t.strip())
        city_raw, district_raw = self._split_location(location_str)

        # --- Features from all text nodes --------------------------------
        area_raw       = self._find_feature(all_texts, r'\d[\d\s]*\s*m²?')
        rooms_raw      = self._find_feature(all_texts, r'\d+\s*(pièces?|pieces?|chambres?|rooms?)', re.IGNORECASE)
        bathrooms_raw  = self._find_feature(all_texts, r'\d+\s*(salles?\s*de\s*bain|sdbs?|bains?|douches?|bathrooms?)', re.IGNORECASE)
        floor_raw      = self._find_feature(all_texts, r'\d+\s*(étages?|etages?|floors?)', re.IGNORECASE)
        year_built_raw = self._find_feature(all_texts, r'\b(19[5-9]\d|20[0-2]\d)\b')

        # Exclude copyright year "2012-2026" from year_built
        if year_built_raw and "avito" in year_built_raw.lower():
            year_built_raw = None

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
            ad_url         = href,
            scraped_at     = scraped_at,
        )

    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _split_location(raw: str):
        if not raw:
            return None, None
        raw = raw.replace(" – ", ",").replace(" - ", ",")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)

    @staticmethod
    def _find_feature(texts: list, pattern: str, flags=0) -> str | None:
        for t in texts:
            if re.search(pattern, t, flags):
                return t[:200]
        return None

    @staticmethod
    def _next_page(response) -> str | None:
        # 1. Explicit rel="next"
        nxt = (
            response.xpath('//a[@rel="next"]/@href').get()
            or response.xpath(
                '//a[contains(@aria-label,"Suivant") or contains(@aria-label,"next")'
                '  or contains(text(),"Suivant") or contains(text(),"›")]/@href'
            ).get()
        )
        if nxt:
            return response.urljoin(nxt)

        # 2. Build ?o=N from current URL
        match = re.search(r'[?&]o=(\d+)', response.url)
        current_page = int(match.group(1)) if match else 1
        next_num = current_page + 1
        base = re.sub(r'([?&])o=\d+', '', response.url).rstrip("&?")
        sep  = "&" if "?" in base else "?"
        return f"{base}{sep}o={next_num}"
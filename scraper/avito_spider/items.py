import scrapy

class ListingItem(scrapy.Item):
    title          = scrapy.Field()
    price_raw      = scrapy.Field()
    city_raw       = scrapy.Field()
    district_raw   = scrapy.Field()
    area_raw       = scrapy.Field()
    rooms_raw      = scrapy.Field()
    bathrooms_raw  = scrapy.Field()
    floor_raw      = scrapy.Field()
    year_built_raw = scrapy.Field()
    ad_url         = scrapy.Field()
    scraped_at     = scrapy.Field()
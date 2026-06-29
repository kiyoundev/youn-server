from app.services.scraper.result import ScraperResult
from app.services.scraper.config import NEXTDATA_PATHS
from app.services.scraper.base import BaseScraper
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.patchright_scraper import PatchrightScraper, AmazonCAScraper
from app.services.scraper.router import RetailerRouter, RETAILER_MAP

__all__ = [
    "ScraperResult",
    "NEXTDATA_PATHS",
    "RETAILER_MAP",
    "BaseScraper",
    "HTTPScraper",
    "PatchrightScraper",
    "AmazonCAScraper",
    "RetailerRouter",
]

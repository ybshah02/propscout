from __future__ import annotations

import logging
import time

import pandas as pd
from homeharvest import scrape_property

from propscout.models import SearchQuery

log = logging.getLogger(__name__)


class RealtorSource:
    """Realtor.com listings via the open-source HomeHarvest library (free, no API key)."""

    name = "realtor"

    def __init__(self, proxy: str | None = None, retries: int = 2, backoff_s: float = 5.0):
        self.proxy = proxy
        self.retries = retries
        self.backoff_s = backoff_s

    def _scrape(self, **kwargs) -> pd.DataFrame:
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                df = scrape_property(**kwargs)
                return df if df is not None else pd.DataFrame()
            except Exception as exc:  # HomeHarvest raises a mix of HTTP/auth errors
                last_exc = exc
                log.warning("realtor scrape failed (attempt %d): %s", attempt + 1, exc)
                if attempt < self.retries:
                    time.sleep(self.backoff_s * (attempt + 1))
        raise RuntimeError(f"Realtor.com scrape failed after retries: {last_exc}") from last_exc

    def search(self, query: SearchQuery) -> pd.DataFrame:
        return self._scrape(
            location=query.location,
            listing_type="for_sale",
            property_type=query.property_types or None,
            radius=query.radius_miles,
            past_days=query.past_days,
            price_min=query.price_min,
            price_max=query.price_max,
            beds_min=query.beds_min,
            beds_max=query.beds_max,
            baths_min=query.baths_min,
            sqft_min=query.sqft_min,
            sqft_max=query.sqft_max,
            lot_sqft_min=query.lot_sqft_min,
            lot_sqft_max=query.lot_sqft_max,
            year_built_min=query.year_built_min,
            exclude_pending=True,
            limit=query.limit,
        )

    def rent_comps(self, query: SearchQuery) -> pd.DataFrame:
        return self._scrape(
            location=query.location,
            listing_type="for_rent",
            radius=query.radius_miles,
            limit=500,
            extra_property_data=False,
        )

    def sold_comps(self, query: SearchQuery, past_days: int = 180) -> pd.DataFrame:
        return self._scrape(
            location=query.location,
            listing_type="sold",
            radius=query.radius_miles,
            past_days=past_days,
            limit=500,
            extra_property_data=False,
        )

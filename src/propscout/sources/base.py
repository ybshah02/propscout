from __future__ import annotations

from typing import Protocol

import pandas as pd

from propscout.models import SearchQuery


class Source(Protocol):
    """A listing source. New adapters (Zillow via Apify, Redfin, LandWatch, ...) implement this.

    All methods return DataFrames using HomeHarvest's column names so downstream code is
    source-agnostic. Adapters must at least provide: property_id, property_url, formatted_address,
    zip_code, list_price, beds, full_baths, sqft, lot_sqft, style.
    """

    name: str

    def search(self, query: SearchQuery) -> pd.DataFrame: ...

    def rent_comps(self, query: SearchQuery) -> pd.DataFrame: ...

    def sold_comps(self, query: SearchQuery, past_days: int = 180) -> pd.DataFrame: ...

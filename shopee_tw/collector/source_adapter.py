"""Interface for approved, zero-cost data feeds.

Do not implement scraping of Shopee behind login, rate limits or anti-bot defenses.
Replace this stub only when a documented, permissioned data source is available.
"""
from pathlib import Path

def collect(brand: str):
    raise NotImplementedError(
        "Shopee TW bulk listing access not configured. "
        "Use sourced CSV ingestion until permitted data access is verified."
    )

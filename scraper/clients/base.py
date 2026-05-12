"""Base class for ATS platform clients."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RawJob:
    """Normalized job data extracted from any ATS platform."""
    title: str
    company: str
    location: str
    url: str
    posted_date: Optional[datetime] = None
    department: Optional[str] = None
    salary_range: str = ""
    company_logo: str = ""
    employment_type: Optional[str] = None
    description: str = ""


class BaseClient:
    """Base class for all ATS platform clients."""
    
    PLATFORM: str = ""
    MAX_RETRIES: int = 3
    RATE_LIMIT_WAIT: int = 60
    REQUEST_DELAY: float = 1.0
    
    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client
    
    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Scrape all jobs from a single company. Override in subclasses."""
        raise NotImplementedError
    
    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """Make HTTP request with retry logic for rate limits."""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._client.request(method, url, **kwargs)
                
                if response.status_code == 429:
                    wait = self.RATE_LIMIT_WAIT * (attempt + 1)
                    logger.warning(f"Rate limited on {url}, waiting {wait}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                    continue
                
                if response.status_code == 404:
                    logger.warning(f"404 Not Found: {url}")
                    return None
                
                if response.status_code >= 500:
                    logger.warning(f"Server error {response.status_code}: {url}")
                    return None
                
                response.raise_for_status()
                return response
                
            except httpx.TimeoutException:
                logger.warning(f"Timeout on {url} (attempt {attempt + 1})")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(5)
            except httpx.HTTPError as e:
                logger.warning(f"HTTP error on {url}: {e}")
                return None
        
        return None

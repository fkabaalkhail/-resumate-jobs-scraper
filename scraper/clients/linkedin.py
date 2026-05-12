"""LinkedIn Public Jobs scraper.

Scrapes LinkedIn's public job search pages (no auth required).
LinkedIn's public search at /jobs/search returns HTML with job listings
that include title, company, location, and direct apply links.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class LinkedInClient(BaseClient):
    """Scrapes jobs from LinkedIn's public job search."""

    PLATFORM = "linkedin"
    MAX_RETRIES = 2
    RATE_LIMIT_WAIT = 30
    REQUEST_DELAY = 3.0  # Be respectful — 3s between requests

    # Search configurations for different locations/keywords
    SEARCHES = [
        # Canada - broad
        {"keywords": "intern software engineer", "location": "Canada", "geo_id": "101174742"},
        {"keywords": "new grad software", "location": "Canada", "geo_id": "101174742"},
        {"keywords": "co-op developer", "location": "Canada", "geo_id": "101174742"},
        {"keywords": "junior software engineer", "location": "Canada", "geo_id": "101174742"},
        {"keywords": "intern data", "location": "Canada", "geo_id": "101174742"},
        {"keywords": "entry level engineer", "location": "Canada", "geo_id": "101174742"},
        # US - broad
        {"keywords": "intern software engineer", "location": "United States", "geo_id": "103644278"},
        {"keywords": "new grad software", "location": "United States", "geo_id": "103644278"},
        {"keywords": "junior developer", "location": "United States", "geo_id": "103644278"},
        {"keywords": "entry level data analyst", "location": "United States", "geo_id": "103644278"},
        {"keywords": "intern machine learning", "location": "United States", "geo_id": "103644278"},
        {"keywords": "associate software engineer", "location": "United States", "geo_id": "103644278"},
    ]

    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Not used for LinkedIn — we use scrape_searches instead."""
        return []

    async def scrape_all_searches(self) -> list[RawJob]:
        """Run all configured searches and return combined results."""
        all_jobs: list[RawJob] = []
        seen_urls: set[str] = set()

        for search in self.SEARCHES:
            try:
                jobs = await self._scrape_search(
                    keywords=search["keywords"],
                    location=search["location"],
                    geo_id=search.get("geo_id", ""),
                )
                # Deduplicate within this run
                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

                logger.info(
                    f"LinkedIn search '{search['keywords']}' in {search['location']}: "
                    f"found {len(jobs)} jobs ({len(all_jobs)} total unique)"
                )
            except Exception as e:
                logger.warning(f"LinkedIn search failed for '{search['keywords']}' in {search['location']}: {e}")

            await asyncio.sleep(self.REQUEST_DELAY)

        return all_jobs

    async def _scrape_search(
        self, keywords: str, location: str, geo_id: str = "", max_pages: int = 2
    ) -> list[RawJob]:
        """Scrape a single LinkedIn job search query (up to max_pages of 25 results each)."""
        jobs: list[RawJob] = []

        for page in range(max_pages):
            start = page * 25
            url = self._build_search_url(keywords, location, geo_id, start)

            response = await self._request_with_retry(
                "GET", url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )

            if not response:
                break

            html = response.text
            page_jobs = self._parse_search_results(html, location)
            jobs.extend(page_jobs)

            # If we got fewer than 25 results, no more pages
            if len(page_jobs) < 20:
                break

            await asyncio.sleep(self.REQUEST_DELAY)

        return jobs

    def _build_search_url(self, keywords: str, location: str, geo_id: str, start: int) -> str:
        """Build LinkedIn public job search URL."""
        params = f"keywords={quote_plus(keywords)}&location={quote_plus(location)}"
        if geo_id:
            params += f"&geoId={geo_id}"
        params += f"&f_TPR=r604800"  # Past week
        params += f"&f_E=1%2C2"  # Entry level + Associate
        params += f"&start={start}"
        return f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{params}"

    def _parse_search_results(self, html: str, search_location: str) -> list[RawJob]:
        """Parse LinkedIn search results HTML into RawJob objects."""
        jobs: list[RawJob] = []

        # Extract job IDs from entity URNs
        job_ids = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)

        # Find titles
        titles = re.findall(
            r'base-search-card__title[^"]*"[^>]*>\s*([^<]+)',
            html
        )

        # Find companies (in the subtitle after the link)
        companies = re.findall(
            r'base-search-card__subtitle[^"]*"[^>]*>\s*\n\s*([^\n<]+)',
            html
        )
        # Clean company names
        companies = [c.strip() for c in companies]

        # Find locations
        locations = re.findall(
            r'job-search-card__location[^"]*"[^>]*>\s*([^<]+)',
            html
        )

        # Find dates
        dates = re.findall(
            r'<time[^>]*datetime="([^"]+)"',
            html
        )

        # Combine into jobs
        count = min(len(job_ids), len(titles))

        for i in range(count):
            title = titles[i].strip() if i < len(titles) else ""
            company = companies[i].strip() if i < len(companies) else ""
            location = locations[i].strip() if i < len(locations) else search_location
            job_id = job_ids[i] if i < len(job_ids) else ""
            date_str = dates[i].strip() if i < len(dates) else ""

            if not title or not job_id:
                continue

            # Build clean LinkedIn job URL
            url = f"https://www.linkedin.com/jobs/view/{job_id}"

            # Parse date
            posted_date = None
            if date_str:
                try:
                    posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            jobs.append(RawJob(
                title=title,
                company=company,
                location=location,
                url=url,
                posted_date=posted_date,
                company_logo=f"https://www.google.com/s2/favicons?domain={company.lower().replace(' ', '')}.com&sz=128" if company else "",
            ))

        return jobs

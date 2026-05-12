"""Main orchestrator for the ATS job scraper pipeline."""

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .registry import load_registry, group_by_platform
from .db import get_session, store_job, normalize_url
from .clients.base import RawJob
from .clients.greenhouse import GreenhouseClient
from .clients.lever import LeverClient
from .clients.ashby import AshbyClient
from .clients.workday import WorkdayClient
from .services.entry_level_filter import EntryLevelFilter
from .services.category_classifier import CategoryClassifier
from .services.location_filter import LocationFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ScrapeStats:
    """Aggregate statistics for a scrape run."""
    total_companies: int = 0
    companies_succeeded: int = 0
    companies_failed: int = 0
    total_jobs_found: int = 0
    jobs_after_filter: int = 0
    new_jobs_stored: int = 0
    duplicates_skipped: int = 0


CLIENT_MAP = {
    "greenhouse": GreenhouseClient,
    "lever": LeverClient,
    "ashby": AshbyClient,
    "workday": WorkdayClient,
}


class ATSScraper:
    """Orchestrates scraping across all configured ATS platforms."""
    
    def __init__(self, db_url: str, companies_path: Optional[str] = None):
        self.db_url = db_url
        self.companies_path = companies_path
        self.entry_filter = EntryLevelFilter()
        self.category_classifier = CategoryClassifier()
        self.location_filter = LocationFilter()
        self.staleness_cutoff = datetime.utcnow() - timedelta(days=30)
    
    async def run(
        self,
        platform_filter: Optional[str] = None,
        company_filter: Optional[str] = None,
    ) -> ScrapeStats:
        """Execute the full scrape pipeline."""
        # Load registry
        companies = load_registry(self.companies_path)
        logger.info(f"Loaded {len(companies)} companies from registry")
        
        # Apply filters
        if platform_filter:
            companies = [c for c in companies if c["ats_platform"] == platform_filter]
        if company_filter:
            companies = [c for c in companies if c["company_name"].lower() == company_filter.lower()]
        
        if not companies:
            logger.warning("No companies to scrape after filtering")
            return ScrapeStats()
        
        # Group by platform
        groups = group_by_platform(companies)
        logger.info(f"Platforms: {', '.join(f'{k}({len(v)})' for k, v in groups.items())}")
        
        # Connect to database
        try:
            session = get_session(self.db_url)
        except Exception as e:
            logger.critical(f"Failed to connect to database: {e}")
            sys.exit(1)
        
        stats = ScrapeStats(total_companies=len(companies))
        
        # Process each platform
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http_client:
            for platform, platform_companies in groups.items():
                client_class = CLIENT_MAP.get(platform)
                if not client_class:
                    logger.warning(f"Unknown platform: {platform}")
                    continue
                
                client = client_class(http_client)
                
                for company in platform_companies:
                    try:
                        raw_jobs = await client.scrape_company(company)
                        stats.total_jobs_found += len(raw_jobs)
                        
                        # Process each job through the pipeline
                        for job in raw_jobs:
                            stored = self._process_job(job, platform, session)
                            if stored:
                                stats.new_jobs_stored += 1
                            elif stored is False:
                                stats.duplicates_skipped += 1
                        
                        stats.companies_succeeded += 1
                    except Exception as e:
                        logger.error(f"Failed to scrape {company['company_name']}: {e}")
                        stats.companies_failed += 1
                    
                    # Delay between companies
                    await asyncio.sleep(client.REQUEST_DELAY)
        
        session.close()
        
        # Log summary
        logger.info(
            f"Scrape complete: {stats.companies_succeeded}/{stats.total_companies} companies, "
            f"{stats.total_jobs_found} found, {stats.new_jobs_stored} new, "
            f"{stats.duplicates_skipped} duplicates"
        )
        
        return stats
    
    def _process_job(self, job: RawJob, platform: str, session) -> Optional[bool]:
        """Process a single job through filters and store if valid.
        
        Returns True if stored, False if duplicate, None if filtered out.
        """
        # Entry-level filter
        filter_result = self.entry_filter.filter(job.title)
        if not filter_result.is_entry_level:
            return None
        
        # Location filter
        loc_result = self.location_filter.filter(job.location)
        if not loc_result.is_included:
            return None
        
        # Staleness check (skip jobs older than 30 days)
        if job.posted_date and job.posted_date.replace(tzinfo=None) < self.staleness_cutoff:
            return None
        
        # Category classification
        role_category = self.category_classifier.classify(job.title, job.department or "")
        
        # Build job data for storage
        job_data = {
            "platform": platform,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "description": job.description,
            "posted_date": job.posted_date.replace(tzinfo=None) if job.posted_date else None,
            "salary_range": job.salary_range,
            "company_logo": job.company_logo,
            "ats_type": platform,
            "work_type": loc_result.work_type,
            "role_category": role_category,
            "country": loc_result.country,
            "experience_level": filter_result.experience_level or "new_grad",
        }
        
        # Store (returns True if new, False if duplicate)
        return store_job(session, job_data)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="ATS Job Scraper")
    parser.add_argument("--platform", choices=["greenhouse", "lever", "ashby", "workday"],
                       help="Scrape only a specific platform")
    parser.add_argument("--company", type=str, help="Scrape a single company by name")
    args = parser.parse_args()
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.critical("DATABASE_URL environment variable is required")
        sys.exit(1)
    
    scraper = ATSScraper(db_url=db_url)
    asyncio.run(scraper.run(
        platform_filter=args.platform,
        company_filter=args.company,
    ))


if __name__ == "__main__":
    main()

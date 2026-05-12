"""Lever ATS platform client."""

import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class LeverClient(BaseClient):
    """Fetches jobs from Lever public postings API."""
    
    PLATFORM = "lever"
    BASE_URL = "https://api.lever.co/v0/postings/{slug}"
    
    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Fetch all postings from a Lever company."""
        slug = company["board_slug"]
        url = self.BASE_URL.format(slug=slug)
        
        response = await self._request_with_retry("GET", url, params={"mode": "json"})
        if not response:
            return []
        
        postings = response.json()
        if not isinstance(postings, list):
            return []
        
        raw_jobs = []
        for posting in postings:
            job = self._parse_posting(posting, company)
            if job:
                raw_jobs.append(job)
        
        logger.info(f"Lever/{slug}: found {len(raw_jobs)} jobs")
        return raw_jobs
    
    def _parse_posting(self, posting: dict, company: dict) -> Optional[RawJob]:
        """Parse a single Lever posting into RawJob."""
        try:
            title = posting.get("text", "")
            if not title:
                return None
            
            # Location from categories
            categories = posting.get("categories", {})
            location = categories.get("location", "") if isinstance(categories, dict) else ""
            
            # URL — use hostedUrl
            url = posting.get("hostedUrl", "")
            if not url:
                return None
            
            # Posted date
            posted_date = None
            created_at = posting.get("createdAt")
            if created_at:
                try:
                    # Lever uses millisecond timestamps
                    posted_date = datetime.fromtimestamp(created_at / 1000)
                except (ValueError, TypeError, OSError):
                    pass
            
            # Department
            department = categories.get("team", "") or categories.get("department", "")
            
            # Employment type / commitment
            employment_type = categories.get("commitment", "")
            
            # Salary - Lever sometimes includes it in the description or additional fields
            salary_range = ""
            description_text = posting.get("descriptionPlain", "") or ""
            additional = posting.get("additional", "") or posting.get("additionalPlain", "") or ""
            combined_text = description_text + " " + additional
            if combined_text.strip():
                import re
                salary_patterns = [
                    r'\$[\d,]+(?:\.\d+)?\s*[-–to]+\s*\$[\d,]+(?:\.\d+)?(?:\s*/\s*(?:yr|year|hr|hour|annually))?',
                    r'\$[\d,]+(?:\.\d+)?\s*/\s*(?:yr|year|hr|hour)',
                ]
                for pattern in salary_patterns:
                    match = re.search(pattern, combined_text, re.IGNORECASE)
                    if match:
                        salary_range = match.group(0)
                        break
            
            # Description from Lever's descriptionPlain field
            description = ""
            desc_plain = posting.get("descriptionPlain", "") or ""
            if desc_plain:
                description = desc_plain.strip()
                if len(description) > 2000:
                    description = description[:2000] + "..."
            
            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=posted_date,
                department=department,
                salary_range=salary_range,
                company_logo=company.get("company_logo_url", ""),
                employment_type=employment_type,
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Lever posting: {e}")
            return None

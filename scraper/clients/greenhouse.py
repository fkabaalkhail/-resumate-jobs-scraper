"""Greenhouse ATS platform client."""

import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class GreenhouseClient(BaseClient):
    """Fetches jobs from Greenhouse public boards API."""
    
    PLATFORM = "greenhouse"
    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    
    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Fetch all jobs from a Greenhouse company board."""
        slug = company["board_slug"]
        url = self.BASE_URL.format(slug=slug)
        
        response = await self._request_with_retry("GET", url, params={"content": "true"})
        if not response:
            return []
        
        data = response.json()
        jobs_data = data.get("jobs", [])
        
        raw_jobs = []
        for job_data in jobs_data:
            job = self._parse_job(job_data, company)
            if job:
                raw_jobs.append(job)
        
        logger.info(f"Greenhouse/{slug}: found {len(raw_jobs)} jobs")
        return raw_jobs
    
    def _parse_job(self, job_data: dict, company: dict) -> Optional[RawJob]:
        """Parse a single Greenhouse job object into RawJob."""
        try:
            title = job_data.get("title", "")
            if not title:
                return None
            
            # Location
            location_obj = job_data.get("location", {})
            location = location_obj.get("name", "") if isinstance(location_obj, dict) else ""
            
            # URL
            job_id = job_data.get("id")
            slug = company["board_slug"]
            url = f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"
            
            # Posted date
            posted_date = None
            updated_at = job_data.get("updated_at") or job_data.get("first_published_at")
            if updated_at:
                try:
                    posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            
            # Department
            departments = job_data.get("departments", [])
            department = departments[0].get("name", "") if departments else ""
            
            # Salary (from metadata if available)
            salary_range = self._extract_salary(job_data)
            
            # Description (from content field)
            description = ""
            content = job_data.get("content", "")
            if content:
                # Strip HTML tags for plain text
                import re
                description = re.sub(r'<[^>]+>', '\n', content)
                description = re.sub(r'\n{3,}', '\n\n', description).strip()
                # Limit to 2000 chars to avoid bloating the DB
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
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Greenhouse job: {e}")
            return None
    
    def _extract_salary(self, job_data: dict) -> str:
        """Extract salary range from Greenhouse job metadata."""
        # Greenhouse sometimes has salary in metadata
        metadata = job_data.get("metadata", [])
        if isinstance(metadata, list):
            for item in metadata:
                if isinstance(item, dict):
                    name = item.get("name", "").lower()
                    if "salary" in name or "compensation" in name:
                        return item.get("value", "")
        return ""

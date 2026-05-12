"""Ashby ATS platform client."""

import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class AshbyClient(BaseClient):
    """Fetches jobs from Ashby posting API."""
    
    PLATFORM = "ashby"
    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
    
    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Fetch all jobs from an Ashby company board."""
        slug = company["board_slug"]
        url = self.BASE_URL.format(slug=slug)
        
        response = await self._request_with_retry("GET", url)
        if not response:
            return []
        
        data = response.json()
        jobs_data = data.get("jobs", [])
        
        raw_jobs = []
        for job_data in jobs_data:
            job = self._parse_job(job_data, company)
            if job:
                raw_jobs.append(job)
        
        logger.info(f"Ashby/{slug}: found {len(raw_jobs)} jobs")
        return raw_jobs
    
    def _parse_job(self, job_data: dict, company: dict) -> Optional[RawJob]:
        """Parse a single Ashby job object into RawJob."""
        try:
            title = job_data.get("title", "")
            if not title:
                return None
            
            # Location
            location = job_data.get("location", "")
            if isinstance(location, dict):
                location = location.get("name", "")
            
            # URL
            url = job_data.get("applyUrl", "") or job_data.get("jobUrl", "")
            if not url:
                return None
            
            # Posted date
            posted_date = None
            published = job_data.get("publishedAt") or job_data.get("createdAt")
            if published:
                try:
                    posted_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            
            # Department
            department = job_data.get("department", "")
            if isinstance(department, dict):
                department = department.get("name", "")
            
            # Employment type
            employment_type = job_data.get("employmentType", "")
            
            # Description from Ashby's descriptionHtml or descriptionPlain field
            description = ""
            desc_html = job_data.get("descriptionHtml", "") or job_data.get("description", "")
            if desc_html:
                import re
                from html import unescape
                description = unescape(desc_html)
                description = re.sub(r'<[^>]+>', '\n', description)
                description = re.sub(r'\n{3,}', '\n\n', description).strip()
                if len(description) > 3000:
                    description = description[:3000] + "..."
            elif job_data.get("descriptionPlain", ""):
                from html import unescape
                description = unescape(job_data["descriptionPlain"]).strip()[:3000]
            
            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=posted_date,
                department=department,
                company_logo=company.get("company_logo_url", ""),
                employment_type=employment_type,
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Ashby job: {e}")
            return None

"""Workday ATS platform client."""

import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class WorkdayClient(BaseClient):
    """Fetches jobs from Workday company career sites."""
    
    PLATFORM = "workday"
    MAX_RETRIES = 2
    RATE_LIMIT_WAIT = 120
    REQUEST_DELAY = 2.0
    
    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Fetch entry-level jobs from a Workday company site."""
        template = company.get("workday_url_template", "")
        if not template:
            logger.warning(f"Workday/{company['company_name']}: no URL template, skipping")
            return []
        
        # Workday uses a search API endpoint
        search_url = template.rstrip("/") + "/search"
        
        payload = self._build_search_payload(company)
        
        response = await self._request_with_retry(
            "POST", search_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if not response:
            return []
        
        try:
            data = response.json()
        except Exception:
            logger.warning(f"Workday/{company['company_name']}: invalid JSON response")
            return []
        
        # Workday response structure varies, try common patterns
        jobs_data = (
            data.get("jobPostings", []) or
            data.get("listItems", []) or
            data.get("body", {}).get("children", []) or
            []
        )
        
        raw_jobs = []
        for job_data in jobs_data:
            job = self._parse_job(job_data, company)
            if job:
                raw_jobs.append(job)
        
        logger.info(f"Workday/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs
    
    def _build_search_payload(self, company: dict) -> dict:
        """Build the POST payload for Workday search API."""
        return {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": "intern OR new grad OR junior OR entry level",
        }
    
    def _parse_job(self, job_data: dict, company: dict) -> Optional[RawJob]:
        """Parse a single Workday job result into RawJob."""
        try:
            title = job_data.get("title", "") or job_data.get("bulletFields", [""])[0] if isinstance(job_data.get("bulletFields"), list) else ""
            if not title:
                title = job_data.get("text", "")
            if not title:
                return None
            
            # Location
            location = ""
            if "locationsText" in job_data:
                location = job_data["locationsText"]
            elif "subtitles" in job_data and job_data["subtitles"]:
                location = job_data["subtitles"][0].get("instances", [{}])[0].get("text", "") if job_data["subtitles"] else ""
            
            # URL
            template = company.get("workday_url_template", "")
            external_path = job_data.get("externalPath", "") or job_data.get("uri", "")
            if external_path:
                url = template.split("/search")[0] + external_path
            else:
                return None
            
            # Posted date
            posted_date = None
            posted = job_data.get("postedOn") or job_data.get("postedDate")
            if posted:
                try:
                    posted_date = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            
            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=posted_date,
                company_logo=company.get("company_logo_url", ""),
            )
        except Exception as e:
            logger.warning(f"Error parsing Workday job: {e}")
            return None

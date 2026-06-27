"""Workday ATS platform client.

Uses the Workday CXS job-board API:
    POST {cxs_base}/jobs   body: {"limit","offset","appliedFacets","searchText"}

where ``cxs_base`` looks like:
    https://{host}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}

The public (apply) URL for a posting is built from the external site host:
    https://{host}.{wdN}.myworkdayjobs.com/{site}{externalPath}

Configure each company with ``workday_url_template`` set to the cxs_base.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class WorkdayClient(BaseClient):
    """Fetches jobs from Workday CXS job boards."""

    PLATFORM = "workday"
    MAX_RETRIES = 2
    RATE_LIMIT_WAIT = 60
    REQUEST_DELAY = 1.5
    PAGE_SIZE = 20
    MAX_PAGES = 10  # cap so a huge board doesn't dominate a run

    async def scrape_company(self, company: dict) -> list[RawJob]:
        """Fetch jobs from a Workday CXS board, paginating through results."""
        cxs_base = (company.get("workday_url_template", "") or "").rstrip("/")
        if not cxs_base or "/wday/cxs/" not in cxs_base:
            logger.warning(
                f"Workday/{company['company_name']}: missing/invalid workday_url_template, skipping"
            )
            return []

        jobs_url = cxs_base + "/jobs"
        raw_jobs: list[RawJob] = []
        offset = 0

        for _ in range(self.MAX_PAGES):
            payload = {
                "limit": self.PAGE_SIZE,
                "offset": offset,
                "appliedFacets": {},
                "searchText": "",
            }
            response = await self._request_with_retry(
                "POST", jobs_url, json=payload,
                headers={"Content-Type": "application/json"},
            )
            if not response:
                break
            try:
                data = response.json()
            except Exception:
                logger.warning(f"Workday/{company['company_name']}: invalid JSON")
                break

            postings = data.get("jobPostings", []) or []
            if not postings:
                break

            for jp in postings:
                job = self._parse_job(jp, company, cxs_base)
                if job:
                    raw_jobs.append(job)

            total = data.get("total", 0)
            offset += self.PAGE_SIZE
            if offset >= total:
                break

        logger.info(f"Workday/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs

    def _public_url(self, cxs_base: str, external_path: str) -> str:
        """Build the public apply URL from the CXS base + externalPath.

        cxs_base: https://{host}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}
        public:   https://{host}.{wdN}.myworkdayjobs.com/{site}{externalPath}
        """
        m = re.match(r"(https://[^/]+)/wday/cxs/[^/]+/([^/]+)", cxs_base)
        if not m:
            return ""
        host_root, site = m.group(1), m.group(2)
        return f"{host_root}/{site}{external_path}"

    def _parse_posted_date(self, posted: str) -> Optional[datetime]:
        """Parse Workday's 'Posted X Days Ago' / 'Posted Today' text."""
        if not posted:
            return None
        text = posted.lower()
        now = datetime.utcnow()
        if "today" in text:
            return now
        if "yesterday" in text:
            return now - timedelta(days=1)
        m = re.search(r"(\d+)\+?\s*day", text)
        if m:
            return now - timedelta(days=int(m.group(1)))
        m = re.search(r"(\d+)\+?\s*month", text)
        if m:
            return now - timedelta(days=30 * int(m.group(1)))
        return None

    def _parse_job(self, jp: dict, company: dict, cxs_base: str) -> Optional[RawJob]:
        """Parse a single Workday jobPosting into a RawJob."""
        try:
            title = jp.get("title", "")
            external_path = jp.get("externalPath", "")
            if not title or not external_path:
                return None

            url = self._public_url(cxs_base, external_path)
            if not url:
                return None

            location = jp.get("locationsText", "")
            # When Workday hides multi-location jobs as "N Locations", the
            # primary city is usually encoded in the externalPath (e.g.
            # /job/Ottawa/Product-Line-Manager_R029960).
            if not location or re.search(r"\d+\s+locations", location.lower()):
                m = re.match(r"/job/([^/]+)/", external_path)
                if m:
                    city = m.group(1).replace("-", " ").strip()
                    location = f"{city} ({location})" if location else city

            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=self._parse_posted_date(jp.get("postedOn", "")),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description="",
            )
        except Exception as e:
            logger.warning(f"Error parsing Workday job: {e}")
            return None

"""TalentPlatform ATS client.

Some companies host careers on a "join.{company}.com" site backed by a vendor
(analytics on talentplatform.us) that exposes a clean public JSON API:

    GET https://{host}/api/jobs?page=N&limit=100
    -> {"jobs": [{"data": {"slug","title","description","full_location",
                           "city","state","country","posted_date","apply_url",
                           "department", ...}}], "totalCount": N}

The public job page is ``https://{host}/jobs/{slug}`` (apply_url is also given).

Configure each company with:
    "ats_platform": "talentplatform",
    "tp_host": "join.kinaxis.com"
"""

import re
import logging
from html import unescape
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class TalentPlatformClient(BaseClient):
    """Fetches jobs from join.{company}.com TalentPlatform career sites."""

    PLATFORM = "talentplatform"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.0
    PAGE_SIZE = 100
    MAX_PAGES = 15

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("tp_host") or "").strip().rstrip("/")
        if not host:
            logger.warning(
                f"TalentPlatform/{company['company_name']}: missing tp_host, skipping"
            )
            return []

        raw_jobs: list[RawJob] = []
        total = None
        for page in range(1, self.MAX_PAGES + 1):
            resp = await self._request_with_retry(
                "GET", f"https://{host}/api/jobs",
                params={"page": page, "limit": self.PAGE_SIZE},
                headers={"Accept": "application/json"},
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                break
            jobs = data.get("jobs", []) or []
            if not jobs:
                break
            for jp in jobs:
                job = self._parse_job(jp.get("data", {}) or {}, company, host)
                if job:
                    raw_jobs.append(job)
            total = data.get("totalCount", total)
            if total is not None and page * self.PAGE_SIZE >= total:
                break

        logger.info(f"TalentPlatform/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(str(value)[:10], "%Y-%m-%d")
            except ValueError:
                return None

    def _parse_job(self, d: dict, company: dict, host: str) -> Optional[RawJob]:
        try:
            title = d.get("title", "")
            slug = d.get("slug") or d.get("req_id")
            if not title or not slug:
                return None
            location = (d.get("full_location") or d.get("short_location")
                        or d.get("location_name") or ", ".join(
                            p for p in [d.get("city"), d.get("state"), d.get("country")] if p))
            url = d.get("apply_url") or f"https://{host}/jobs/{slug}"
            description = ""
            raw = (d.get("description") or "")
            for extra in ("responsibilities", "qualifications"):
                if d.get(extra):
                    raw += "\n" + d[extra]
            if raw.strip():
                description = re.sub(r"<[^>]+>", "\n", unescape(raw))
                description = re.sub(r"\n{3,}", "\n\n", description).strip()[:5000]
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=location or "",
                url=url,
                posted_date=self._parse_date(d.get("posted_date")),
                department=d.get("department", ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing TalentPlatform job: {e}")
            return None

"""BambooHR ATS client.

BambooHR-hosted career pages expose a public JSON list + detail API:

    list:   GET https://{sub}.bamboohr.com/careers/list
            -> {"result": [{"id","jobOpeningName","location":{city,state},
                            "employmentStatusLabel","departmentLabel", ...}]}
    detail: GET https://{sub}.bamboohr.com/careers/{id}/detail
            -> {"result": {"jobOpening": {...,"description": "<html>"}}}

The public job page is ``https://{sub}.bamboohr.com/careers/{id}``.

Configure each company with:
    "ats_platform": "bamboohr",
    "bamboohr_subdomain": "solace"
"""

import re
import logging
from html import unescape
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class BambooHRClient(BaseClient):
    """Fetches jobs from BambooHR-hosted career pages."""

    PLATFORM = "bamboohr"
    MAX_RETRIES = 2
    REQUEST_DELAY = 0.5
    MAX_DETAILS = 120

    async def scrape_company(self, company: dict) -> list[RawJob]:
        sub = (company.get("bamboohr_subdomain") or company.get("board_slug") or "").strip()
        if not sub:
            logger.warning(
                f"BambooHR/{company['company_name']}: missing bamboohr_subdomain, skipping"
            )
            return []

        resp = await self._request_with_retry(
            "GET", f"https://{sub}.bamboohr.com/careers/list",
            headers={"Accept": "application/json"},
        )
        if not resp:
            return []
        try:
            results = resp.json().get("result", []) or []
        except Exception:
            return []

        raw_jobs: list[RawJob] = []
        for i, jp in enumerate(results):
            description = ""
            if i < self.MAX_DETAILS:
                description = await self._fetch_description(sub, jp.get("id"))
            job = self._parse_job(jp, company, sub, description)
            if job:
                raw_jobs.append(job)

        logger.info(f"BambooHR/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs

    async def _fetch_description(self, sub: str, job_id) -> str:
        if not job_id:
            return ""
        resp = await self._request_with_retry(
            "GET", f"https://{sub}.bamboohr.com/careers/{job_id}/detail",
            headers={"Accept": "application/json"},
        )
        if not resp:
            return ""
        try:
            jo = (resp.json().get("result") or {}).get("jobOpening") or {}
        except Exception:
            return ""
        html = jo.get("description") or ""
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", "\n", unescape(html))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text[:5000]

    @staticmethod
    def _location(jp: dict) -> str:
        loc = jp.get("location") or {}
        if isinstance(loc, dict):
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            out = ", ".join(p for p in parts if p)
            if out:
                return out
        if jp.get("isRemote"):
            return "Remote"
        return jp.get("locationName") or ""

    def _parse_job(self, jp: dict, company: dict, sub: str, description: str) -> Optional[RawJob]:
        try:
            job_id = jp.get("id")
            title = jp.get("jobOpeningName") or jp.get("title") or ""
            if not job_id or not title:
                return None
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=self._location(jp),
                url=f"https://{sub}.bamboohr.com/careers/{job_id}",
                posted_date=None,
                department=jp.get("departmentLabel", ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing BambooHR job: {e}")
            return None

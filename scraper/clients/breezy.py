"""Breezy HR ATS client.

Breezy-hosted career pages expose a public JSON feed:

    GET https://{sub}.breezy.hr/json
    -> [{"name","location":{"name",...},"type":{"name"},"url",
         "description":"<html>","published_date", ...}]

Configure each company with:
    "ats_platform": "breezy",
    "breezy_subdomain": "vosyn"
"""

import re
import logging
from html import unescape
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class BreezyClient(BaseClient):
    """Fetches jobs from Breezy HR career pages."""

    PLATFORM = "breezy"
    MAX_RETRIES = 2
    REQUEST_DELAY = 0.5

    async def scrape_company(self, company: dict) -> list[RawJob]:
        sub = (company.get("breezy_subdomain") or company.get("board_slug") or "").strip()
        if not sub:
            logger.warning(
                f"Breezy/{company['company_name']}: missing breezy_subdomain, skipping"
            )
            return []

        resp = await self._request_with_retry(
            "GET", f"https://{sub}.breezy.hr/json", headers={"Accept": "application/json"},
        )
        if not resp:
            return []
        try:
            postings = resp.json()
        except Exception:
            return []
        if not isinstance(postings, list):
            return []

        raw_jobs: list[RawJob] = []
        for jp in postings:
            job = self._parse_job(jp, company, sub)
            if job:
                raw_jobs.append(job)
        logger.info(f"Breezy/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return None

    def _parse_job(self, jp: dict, company: dict, sub: str) -> Optional[RawJob]:
        try:
            title = jp.get("name", "")
            if not title:
                return None
            loc = jp.get("location") or {}
            if isinstance(loc, dict):
                location = loc.get("name") or ", ".join(
                    p for p in [(loc.get("city") or {}).get("name") if isinstance(loc.get("city"), dict) else loc.get("city"),
                                (loc.get("country") or {}).get("name") if isinstance(loc.get("country"), dict) else loc.get("country")] if p
                )
            else:
                location = str(loc)
            url = jp.get("url") or f"https://{sub}.breezy.hr/p/{jp.get('_id','')}"
            description = ""
            html = jp.get("description") or ""
            if html:
                description = re.sub(r"<[^>]+>", "\n", unescape(html))
                description = re.sub(r"\n{3,}", "\n\n", description).strip()[:5000]
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=location or "",
                url=url,
                posted_date=self._parse_date(jp.get("published_date") or jp.get("creation_date")),
                department=(jp.get("department") or ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Breezy job: {e}")
            return None

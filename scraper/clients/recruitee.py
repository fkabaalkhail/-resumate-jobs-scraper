"""Recruitee ATS client.

Recruitee career sites expose a public JSON API:

    GET https://{company}.recruitee.com/api/offers/
    -> {"offers": [{"title","location","city","country","careers_url",
                    "department","description","requirements","published_at", ...}]}

Configure each company with:
    "ats_platform": "recruitee",
    "recruitee_subdomain": "huaweicanada"
"""

import re
import logging
from html import unescape
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class RecruiteeClient(BaseClient):
    """Fetches jobs from Recruitee career sites."""

    PLATFORM = "recruitee"
    MAX_RETRIES = 2
    REQUEST_DELAY = 0.5

    async def scrape_company(self, company: dict) -> list[RawJob]:
        sub = (company.get("recruitee_subdomain") or company.get("board_slug") or "").strip()
        if not sub:
            logger.warning(
                f"Recruitee/{company['company_name']}: missing recruitee_subdomain, skipping"
            )
            return []

        resp = await self._request_with_retry(
            "GET", f"https://{sub}.recruitee.com/api/offers/",
            headers={"Accept": "application/json"},
        )
        if not resp:
            return []
        try:
            offers = resp.json().get("offers", []) or []
        except Exception:
            return []

        raw_jobs: list[RawJob] = []
        for o in offers:
            job = self._parse_job(o, company, sub)
            if job:
                raw_jobs.append(job)
        logger.info(f"Recruitee/{company['company_name']}: found {len(raw_jobs)} jobs")
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

    def _parse_job(self, o: dict, company: dict, sub: str) -> Optional[RawJob]:
        try:
            title = o.get("title", "")
            if not title:
                return None
            location = o.get("location") or ", ".join(
                p for p in [o.get("city"), o.get("state_name"), o.get("country")] if p
            )
            url = o.get("careers_url") or o.get("careers_apply_url") or f"https://{sub}.recruitee.com/o/{o.get('slug','')}"
            description = ""
            raw = (o.get("description") or "") + "\n" + (o.get("requirements") or "")
            if raw.strip():
                description = re.sub(r"<[^>]+>", "\n", unescape(raw))
                description = re.sub(r"\n{3,}", "\n\n", description).strip()[:5000]
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=location or "",
                url=url,
                posted_date=self._parse_date(o.get("published_at")),
                department=o.get("department", ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Recruitee job: {e}")
            return None

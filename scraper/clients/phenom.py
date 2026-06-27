"""Phenom People ATS client.

Phenom-powered career sites (e.g. Roche, Molson Coors) expose a single JSON
endpoint used by their job board:

    POST https://{host}/widgets
    body: {"ddoKey":"refineSearch", "from":N, "size":M, "country":"global",
           "lang":"en_global", "jobs":true, "counts":true, ...}

Response: ``{"refineSearch": {"data": {"jobs": [...]}}}``. There is no total
count field, so we paginate by ``from`` until a short page is returned.

Per-job fields include ``title``, ``jobSeqNo``, ``location``/``cityState``,
``postedDate``, ``descriptionTeaser`` (a short summary) and sometimes
``applyUrl``. The public job page is ``https://{host}/job/{jobSeqNo}``.

Configure each company with:
    "ats_platform": "phenom",
    "phenom_host": "careers.roche.com"
    "phenom_country": "global"   (optional, default "global")
    "phenom_lang": "en_global"   (optional, default "en_global")
"""

import re
import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class PhenomClient(BaseClient):
    """Fetches jobs from Phenom People career sites."""

    PLATFORM = "phenom"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.0
    PAGE_SIZE = 20
    MAX_PAGES = 20  # cap (20 * 20 = 400 postings scanned)

    def _body(self, country: str, lang: str, frm: int) -> dict:
        return {
            "lang": lang, "deviceType": "desktop", "country": country,
            "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "",
            "subsearch": "", "from": frm, "irs": False, "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "state", "city", "type"],
            "size": self.PAGE_SIZE, "clearAll": False, "jdsource": "facets",
            "pageId": "page11-ds", "siteType": "external", "keywords": "",
            "global": True, "selected_fields": {}, "locationData": {},
        }

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("phenom_host") or "").strip().rstrip("/")
        country = (company.get("phenom_country") or "global").strip()
        lang = (company.get("phenom_lang") or "en_global").strip()
        if not host:
            logger.warning(
                f"Phenom/{company['company_name']}: missing phenom_host, skipping"
            )
            return []

        try:
            await self._client.get(f"https://{host}/")
        except Exception:
            pass

        api = f"https://{host}/widgets"
        raw_jobs: list[RawJob] = []
        frm = 0
        for _ in range(self.MAX_PAGES):
            resp = await self._request_with_retry(
                "POST", api, json=self._body(country, lang, frm),
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         "X-Requested-With": "XMLHttpRequest"},
            )
            if not resp:
                break
            try:
                data = (resp.json().get("refineSearch") or {}).get("data") or {}
            except Exception:
                break
            jobs = data.get("jobs") or []
            if not jobs:
                break
            for jp in jobs:
                job = self._parse_job(jp, company, host)
                if job:
                    raw_jobs.append(job)
            if len(jobs) < self.PAGE_SIZE:
                break
            frm += self.PAGE_SIZE

        logger.info(f"Phenom/{company['company_name']}: found {len(raw_jobs)} jobs")
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

    def _parse_job(self, jp: dict, company: dict, host: str) -> Optional[RawJob]:
        try:
            title = jp.get("title", "")
            seq = jp.get("jobSeqNo") or jp.get("jobId")
            if not title or not seq:
                return None
            location = (jp.get("location") or jp.get("cityState")
                        or jp.get("cityStateCountry") or "")
            url = jp.get("applyUrl") or f"https://{host}/job/{seq}"
            description = jp.get("descriptionTeaser") or ""
            if description:
                description = re.sub(r"\s+", " ", description).strip()[:3000]
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=self._parse_date(jp.get("postedDate")),
                department=jp.get("category", ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Phenom job: {e}")
            return None

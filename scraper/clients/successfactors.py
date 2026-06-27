"""SAP SuccessFactors (Career Site Builder) ATS client.

Modern SuccessFactors career sites expose a public JSON search endpoint used by
their own job board:

    POST https://{host}/services/recruiting/v1/jobs
    body: {"locale":"en_US","pageNumber":N,"sortBy":"","keywords":"","location":"",
           "facetFilters":{},"brand":"","skills":[],"categoryId":0,
           "alertId":"","rcmCandidateId":""}

A session cookie (JSESSIONID) from first loading the careers homepage is
required. The response is ``{"jobSearchResult": [{"response": {...}}],
"totalJobs": N}`` paginated 10 per page by ``pageNumber``.

Per-job ``response`` fields: ``id``, ``unifiedStandardTitle`` (title),
``jobLocationShort`` (location), ``urlTitle`` (slug). The public job URL is
``https://{host}/job/{id}``.

Configure each company with:
    "ats_platform": "successfactors",
    "sf_host": "jobs.bombardier.com"
"""

import re
import logging
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class SuccessFactorsClient(BaseClient):
    """Fetches jobs from SAP SuccessFactors Career Site Builder sites."""

    PLATFORM = "successfactors"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.0
    PAGE_SIZE = 10          # SF CSB default page size
    MAX_PAGES = 30          # cap (30 * 10 = 300 postings scanned)

    def _body(self, page_no: int) -> dict:
        return {
            "locale": "en_US", "pageNumber": page_no, "sortBy": "",
            "keywords": "", "location": "", "facetFilters": {}, "brand": "",
            "skills": [], "categoryId": 0, "alertId": "", "rcmCandidateId": "",
        }

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("sf_host") or "").strip().rstrip("/")
        if not host:
            logger.warning(
                f"SuccessFactors/{company['company_name']}: missing sf_host, skipping"
            )
            return []

        # Establish the JSESSIONID cookie the API requires.
        try:
            await self._client.get(f"https://{host}/")
        except Exception:
            pass

        api = f"https://{host}/services/recruiting/v1/jobs"
        raw_jobs: list[RawJob] = []
        total = None

        for page in range(self.MAX_PAGES):
            resp = await self._request_with_retry(
                "POST", api, json=self._body(page),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                logger.warning(f"SuccessFactors/{company['company_name']}: invalid JSON")
                break

            results = data.get("jobSearchResult", []) or []
            if not results:
                break
            for item in results:
                job = self._parse_job(item.get("response", {}) or {}, company, host)
                if job:
                    raw_jobs.append(job)

            total = data.get("totalJobs", total)
            if total is not None and (page + 1) * self.PAGE_SIZE >= total:
                break

        logger.info(
            f"SuccessFactors/{company['company_name']}: found {len(raw_jobs)} jobs"
        )
        return raw_jobs

    @staticmethod
    def _clean_location(value) -> str:
        if isinstance(value, list):
            parts = [re.sub(r"<[^>]+>", "", str(v)).strip() for v in value if v]
            return "; ".join(p for p in parts if p)
        return re.sub(r"<[^>]+>", "", str(value or "")).strip()

    def _parse_job(self, resp: dict, company: dict, host: str) -> Optional[RawJob]:
        try:
            job_id = resp.get("id")
            title = (resp.get("unifiedStandardTitle")
                     or resp.get("jobTitle") or resp.get("title") or "")
            if not job_id or not title:
                return None
            location = self._clean_location(resp.get("jobLocationShort"))
            url = f"https://{host}/job/{job_id}"
            return RawJob(
                title=title.strip(),
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=None,
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description="",
            )
        except Exception as e:
            logger.warning(f"Error parsing SuccessFactors job: {e}")
            return None

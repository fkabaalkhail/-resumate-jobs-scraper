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
from urllib.parse import unquote
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class SuccessFactorsClient(BaseClient):
    """Fetches jobs from SAP SuccessFactors career sites.

    Supports two flavours:
    - Career Site Builder (CSB): JSON API at /services/recruiting/v1/jobs.
    - Recruiting Marketing (RMK): server-rendered /search/ HTML (older sites,
      e.g. Bank of Canada). Used automatically when the CSB API isn't available.
    """

    PLATFORM = "successfactors"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.0
    PAGE_SIZE = 10          # SF CSB default page size
    MAX_PAGES = 30          # cap (30 * 10 = 300 postings scanned)
    RMK_PAGE_SIZE = 25      # SF RMK fixed page size
    RMK_MAX_PAGES = 16

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

        mode = (company.get("sf_mode") or "auto").strip().lower()

        # Establish a session cookie.
        try:
            await self._client.get(f"https://{host}/")
        except Exception:
            pass

        if mode in ("auto", "csb"):
            jobs = await self._scrape_csb(company, host)
            if jobs or mode == "csb":
                return jobs
            # CSB yielded nothing — fall back to the RMK server-rendered site.
        return await self._scrape_rmk(company, host)

    async def _scrape_csb(self, company: dict, host: str) -> list[RawJob]:
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

        if raw_jobs:
            logger.info(
                f"SuccessFactors/{company['company_name']} (CSB): found {len(raw_jobs)} jobs"
            )
        return raw_jobs

    async def _scrape_rmk(self, company: dict, host: str) -> list[RawJob]:
        """Scrape the older server-rendered RMK /search/ pages."""
        raw_jobs: list[RawJob] = []
        startrow = 0
        for _ in range(self.RMK_MAX_PAGES):
            resp = await self._request_with_retry(
                "GET", f"https://{host}/search/",
                params={"startrow": startrow},
                headers={"Accept": "text/html"},
            )
            if not resp:
                break
            rows = re.findall(
                r'<tr[^>]*class="data-row"[^>]*>(.*?)</tr>', resp.text, re.DOTALL
            )
            if not rows:
                break
            for row in rows:
                job = self._parse_rmk_row(row, company, host)
                if job:
                    raw_jobs.append(job)
            if len(rows) < self.RMK_PAGE_SIZE:
                break
            startrow += self.RMK_PAGE_SIZE

        logger.info(
            f"SuccessFactors/{company['company_name']} (RMK): found {len(raw_jobs)} jobs"
        )
        return raw_jobs

    def _parse_rmk_row(self, row: str, company: dict, host: str) -> Optional[RawJob]:
        try:
            href_m = re.search(r'href="(/job/([^"]+?)/(\d+)/?)"', row)
            title_m = re.search(r'jobTitle-link[^>]*>([^<]+)<', row)
            if not href_m or not title_m:
                return None
            href, slug, _job_id = href_m.group(1), href_m.group(2), href_m.group(3)
            title = title_m.group(1).strip()
            if not title:
                return None
            # Location is embedded in the slug: "{Location}-{Title}-{Prov}".
            decoded = unquote(slug).replace("-", " ")
            location = decoded.replace(title, " ").strip()
            location = re.sub(r"\s{2,}", " ", location)
            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=f"https://{host}{href}",
                posted_date=None,
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description="",
            )
        except Exception as e:
            logger.warning(f"Error parsing SuccessFactors RMK row: {e}")
            return None

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

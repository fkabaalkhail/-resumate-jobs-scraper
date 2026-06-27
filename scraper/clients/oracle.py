"""Oracle Recruiting Cloud (ORC) ATS platform client.

Many large enterprises (e.g. Nokia) run their careers site on Oracle Fusion
Recruiting Cloud. The public job feed is served by the HCM REST API:

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true
        &expand=requisitionList.secondaryLocations
        &finder=findReqs;siteNumber={site},facetsList=LOCATIONS,limit=N,offset=M,sortBy=POSTING_DATES_DESC

The response is ``items[0].requisitionList`` (the page) plus
``items[0].TotalJobsCount`` for pagination. Full descriptions live behind a
per-job detail endpoint:

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
        ?expand=all&onlyData=true&finder=ById;Id={Id},siteNumber={site}

returning ``ExternalDescriptionStr`` / ``ExternalResponsibilitiesStr`` /
``ExternalQualificationsStr`` (HTML).

Configure each company with:
    "ats_platform": "oracle",
    "oracle_host":  "fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com",
    "oracle_site":  "CX_1",
    "oracle_careers_host": "jobs.nokia.com"   # public apply-URL host
"""

import re
import asyncio
import logging
from datetime import datetime
from html import unescape
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class OracleClient(BaseClient):
    """Fetches jobs from Oracle Recruiting Cloud (Fusion) career sites."""

    PLATFORM = "oracle"
    MAX_RETRIES = 2
    RATE_LIMIT_WAIT = 60
    REQUEST_DELAY = 1.5
    PAGE_SIZE = 50
    MAX_PAGES = 16          # cap list scan (16 * 50 = 800 postings)
    DETAIL_DELAY = 0.3      # politeness delay between description fetches
    MAX_DETAILS = 200       # cap description fetches per company per run

    # Only fetch full details / keep jobs in these countries (dashboard is NA).
    NA_COUNTRIES = {"US", "CA"}

    def _api_base(self, host: str) -> str:
        return f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    def _detail_base(self, host: str) -> str:
        return f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("oracle_host") or "").strip()
        site = (company.get("oracle_site") or "CX_1").strip()
        careers_host = (company.get("oracle_careers_host") or host).strip()
        if not host:
            logger.warning(
                f"Oracle/{company['company_name']}: missing oracle_host, skipping"
            )
            return []

        api_base = self._api_base(host)
        na_postings: list[dict] = []
        offset = 0

        for _ in range(self.MAX_PAGES):
            finder = (
                f"findReqs;siteNumber={site},facetsList=LOCATIONS,"
                f"limit={self.PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC"
            )
            resp = await self._request_with_retry(
                "GET", api_base,
                params={
                    "onlyData": "true",
                    "expand": "requisitionList.secondaryLocations",
                    "finder": finder,
                },
                headers={"Accept": "application/json"},
            )
            if not resp:
                break
            try:
                items = resp.json().get("items", []) or []
            except Exception:
                logger.warning(f"Oracle/{company['company_name']}: invalid JSON")
                break
            if not items:
                break

            block = items[0]
            req_list = block.get("requisitionList", []) or []
            if not req_list:
                break

            for jp in req_list:
                country = (jp.get("PrimaryLocationCountry") or "").upper()
                secondary = jp.get("secondaryLocations") or []
                sec_countries = {
                    (s.get("CountryCode") or "").upper() for s in secondary
                    if isinstance(s, dict)
                }
                if country in self.NA_COUNTRIES or sec_countries & self.NA_COUNTRIES:
                    na_postings.append(jp)

            total = block.get("TotalJobsCount", 0) or 0
            offset += self.PAGE_SIZE
            if offset >= total:
                break

        # Fetch descriptions for the NA subset (capped) and build RawJobs.
        raw_jobs: list[RawJob] = []
        for i, jp in enumerate(na_postings):
            description = ""
            if i < self.MAX_DETAILS:
                description = await self._fetch_description(
                    host, site, jp.get("Id")
                )
                await asyncio.sleep(self.DETAIL_DELAY)
            job = self._parse_job(jp, company, site, careers_host, description)
            if job:
                raw_jobs.append(job)

        logger.info(
            f"Oracle/{company['company_name']}: scanned {offset} postings, "
            f"{len(na_postings)} in US/CA, returning {len(raw_jobs)} jobs"
        )
        return raw_jobs

    async def _fetch_description(self, host: str, site: str, job_id) -> str:
        """Fetch and flatten the external description for a single requisition."""
        if not job_id:
            return ""
        finder = f"ById;Id={job_id},siteNumber={site}"
        resp = await self._request_with_retry(
            "GET", self._detail_base(host),
            params={"expand": "all", "onlyData": "true", "finder": finder},
            headers={"Accept": "application/json"},
        )
        if not resp:
            return ""
        try:
            items = resp.json().get("items", []) or []
        except Exception:
            return ""
        if not items:
            return ""
        detail = items[0]
        parts: list[str] = []
        for key in (
            "ExternalDescriptionStr",
            "ExternalResponsibilitiesStr",
            "ExternalQualificationsStr",
        ):
            html = detail.get(key) or ""
            if html:
                parts.append(html)
        if not parts:
            return ""
        combined = "\n".join(parts)
        text = unescape(combined)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) > 5000:
            text = text[:5000] + "..."
        return text

    def _parse_posted_date(self, value: str) -> Optional[datetime]:
        """Parse an ISO date like '2026-06-27' into a datetime."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d")
            except ValueError:
                return None

    def _parse_job(
        self, jp: dict, company: dict, site: str, careers_host: str, description: str
    ) -> Optional[RawJob]:
        try:
            title = jp.get("Title", "")
            job_id = jp.get("Id")
            if not title or not job_id:
                return None

            url = f"https://{careers_host}/en/sites/{site}/job/{job_id}"

            location = jp.get("PrimaryLocation", "") or ""
            secondary = jp.get("secondaryLocations") or []
            extra = [
                s.get("Name", "") for s in secondary
                if isinstance(s, dict) and s.get("Name")
            ]
            if extra:
                location = f"{location} (+{len(extra)} more)" if location else extra[0]

            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=self._parse_posted_date(jp.get("PostedDate", "")),
                department=jp.get("JobFamily", "") or jp.get("JobFunction", ""),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Oracle job: {e}")
            return None

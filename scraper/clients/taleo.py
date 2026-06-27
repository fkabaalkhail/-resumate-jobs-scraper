"""Taleo (Oracle Taleo Business Edition) ATS client.

Taleo career sites expose a public JSON search endpoint used by their own
job board UI:

    POST https://{host}/careersection/rest/jobboard/searchjobs?lang=en&portal={portal}
    body: a default search payload (keyword/location empty), paginated by pageNo

The response is ``requisitionList`` where each item has ``jobId`` and a
positional ``column`` array (``[title, locationJSON, datePosted]``) plus
``locationsColumns`` indicating which column holds the location. Pagination
metadata is in ``pagingData`` (``totalCount`` / ``pageSize``).

Taleo serves responses with a broken Content-Encoding header, so requests must
send ``Accept-Encoding: identity``. A session cookie from first loading the
careersection page is also required.

Configure each company with:
    "ats_platform": "taleo",
    "taleo_host":    "agnicoeagle.taleo.net",
    "taleo_portal":  "101430233",
    "taleo_section": "2"          # used to build the public job-detail URL
"""

import re
import json
import logging
from datetime import datetime
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)

_HDRS = {
    "Accept-Encoding": "identity",
    "Accept": "application/json, text/plain, */*",
    "tz": "GMT",
}


class TaleoClient(BaseClient):
    """Fetches jobs from Oracle Taleo career sites."""

    PLATFORM = "taleo"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.5
    PAGE_SIZE = 25          # Taleo's fixed page size
    MAX_PAGES = 24          # cap (24 * 25 = 600 postings)

    def _search_body(self, page_no: int) -> dict:
        return {
            "multilineEnabled": False,
            "sortingSelection": {
                "ascendingSortingOrder": "false",
                "sortBySelectionParam": "3",  # sort by posting date desc
            },
            "fieldData": {"fields": {"KEYWORD": "", "LOCATION": ""}, "valid": True},
            "filterSelectionParam": {"searchFilterSelections": []},
            "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []},
            "pageNo": page_no,
        }

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("taleo_host") or "").strip().rstrip("/")
        portal = (company.get("taleo_portal") or "").strip()
        section = (company.get("taleo_section") or "2").strip()
        if not host or not portal:
            logger.warning(
                f"Taleo/{company['company_name']}: missing taleo_host/taleo_portal, skipping"
            )
            return []

        # Establish a session cookie (Taleo rejects the REST call otherwise).
        try:
            await self._client.get(
                f"https://{host}/careersection/{section}/jobsearch.ftl?lang=en",
                headers={**_HDRS, "Accept": "text/html"},
            )
        except Exception:
            pass

        search_url = (
            f"https://{host}/careersection/rest/jobboard/searchjobs"
            f"?lang=en&portal={portal}"
        )
        raw_jobs: list[RawJob] = []
        total = None

        for page in range(1, self.MAX_PAGES + 1):
            resp = await self._request_with_retry(
                "POST", search_url, json=self._search_body(page),
                headers={**_HDRS, "Content-Type": "application/json"},
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                logger.warning(f"Taleo/{company['company_name']}: invalid JSON")
                break

            reqs = data.get("requisitionList", []) or []
            if not reqs:
                break
            for r in reqs:
                job = self._parse_job(r, company, host, section)
                if job:
                    raw_jobs.append(job)

            paging = data.get("pagingData", {}) or {}
            total = paging.get("totalCount", total)
            if total is not None and page * self.PAGE_SIZE >= total:
                break

        logger.info(
            f"Taleo/{company['company_name']}: found {len(raw_jobs)} jobs"
        )
        return raw_jobs

    @staticmethod
    def _parse_location(column: list, locations_columns) -> str:
        idx = None
        if isinstance(locations_columns, list) and locations_columns:
            idx = locations_columns[0]
        if idx is None or idx >= len(column):
            # fall back to the second column (Taleo default layout)
            idx = 1 if len(column) > 1 else 0
        raw = column[idx] if idx < len(column) else ""
        # Location cells look like '["Nunavut"]' or '["US-Tennessee-Piney Flats"]'.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parts = [str(p) for p in parsed if p]
                loc = "; ".join(parts)
            else:
                loc = str(parsed)
        except (json.JSONDecodeError, TypeError):
            loc = re.sub(r'[\[\]"]', "", str(raw)).strip()
        return loc

    @staticmethod
    def _parse_date(column: list) -> Optional[datetime]:
        if not column:
            return None
        candidate = str(column[-1]).strip()
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
        return None

    def _parse_job(
        self, r: dict, company: dict, host: str, section: str
    ) -> Optional[RawJob]:
        try:
            job_id = r.get("jobId")
            column = r.get("column", []) or []
            if not job_id or not column:
                return None
            title = str(column[0]).strip()
            if not title:
                return None

            location = self._parse_location(column, r.get("locationsColumns"))
            url = (
                f"https://{host}/careersection/{section}/jobdetail.ftl"
                f"?job={job_id}&lang=en"
            )
            return RawJob(
                title=title,
                company=company["company_name"],
                location=location,
                url=url,
                posted_date=self._parse_date(column),
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description="",
            )
        except Exception as e:
            logger.warning(f"Error parsing Taleo job: {e}")
            return None

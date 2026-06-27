"""Jobvite ATS client.

Jobvite career sites render the job list as server-side HTML:

    GET https://jobs.jobvite.com/careers/{company}/jobs
    rows: <td class="jv-job-list-name"><a href="/{company}/job/{id}">{title}</a></td>
          <td class="jv-job-list-location">{location}</td>

The public job page is ``https://jobs.jobvite.com{href}``.

Configure each company with:
    "ats_platform": "jobvite",
    "jobvite_company": "ross-video-careers"
"""

import re
import logging
from html import unescape
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)


class JobviteClient(BaseClient):
    """Fetches jobs from Jobvite career sites (HTML)."""

    PLATFORM = "jobvite"
    MAX_RETRIES = 2
    REQUEST_DELAY = 1.0

    _ROW_RE = re.compile(
        r'<td[^>]*class="jv-job-list-name"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<td[^>]*class="jv-job-list-location"[^>]*>(.*?)</td>',
        re.DOTALL,
    )

    async def scrape_company(self, company: dict) -> list[RawJob]:
        slug = (company.get("jobvite_company") or company.get("board_slug") or "").strip()
        if not slug:
            logger.warning(
                f"Jobvite/{company['company_name']}: missing jobvite_company, skipping"
            )
            return []

        resp = await self._request_with_retry(
            "GET", f"https://jobs.jobvite.com/careers/{slug}/jobs",
            headers={"Accept": "text/html"},
        )
        if not resp:
            return []

        raw_jobs: list[RawJob] = []
        for href, title_html, loc_html in self._ROW_RE.findall(resp.text):
            job = self._parse_row(href, title_html, loc_html, company)
            if job:
                raw_jobs.append(job)
        logger.info(f"Jobvite/{company['company_name']}: found {len(raw_jobs)} jobs")
        return raw_jobs

    @staticmethod
    def _clean(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", unescape(html or ""))
        return re.sub(r"\s{2,}", " ", text).strip().strip(",").strip()

    def _parse_row(self, href: str, title_html: str, loc_html: str, company: dict) -> Optional[RawJob]:
        try:
            title = self._clean(title_html)
            if not title:
                return None
            url = href if href.startswith("http") else f"https://jobs.jobvite.com{href}"
            return RawJob(
                title=title,
                company=company["company_name"],
                location=self._clean(loc_html),
                url=url,
                posted_date=None,
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description="",
            )
        except Exception as e:
            logger.warning(f"Error parsing Jobvite row: {e}")
            return None

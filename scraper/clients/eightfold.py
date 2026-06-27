"""Eightfold ATS client (headless browser).

Eightfold career sites (e.g. Ericsson) sit behind HUMAN/PerimeterX bot
protection, so their JSON APIs return 403 to plain HTTP clients. We use a
headless Chromium browser (Playwright) to load the public careers page — which
clears the JS bot challenge and sets the session cookies — and then call the
site's own ``/api/pcsx/*`` endpoints from inside that authenticated page
context.

    search:  https://{host}/api/pcsx/search?domain={domain}&query=&location=
                 &start={offset}&num={n}&sort_by=relevance
             -> data.positions[], data.count
    detail:  https://{host}/api/pcsx/position_details?position_id={id}
                 &domain={domain}&hl=en
             -> data.jobDescription (HTML)

Configure each company with:
    "ats_platform": "eightfold",
    "eightfold_host":   "ericsson.eightfold.ai",
    "eightfold_domain": "ericsson.com",
    "eightfold_careers_url": "https://ericsson.eightfold.ai/careers"   # optional

Requires the ``playwright`` package and a Chromium build
(``playwright install chromium``). If Playwright is unavailable the client
logs a warning and returns no jobs instead of crashing the whole run.
"""

import re
import json
import logging
from datetime import datetime
from html import unescape
from typing import Optional

from .base import BaseClient, RawJob

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class EightfoldClient(BaseClient):
    """Fetches jobs from Eightfold career sites via a headless browser."""

    PLATFORM = "eightfold"
    PAGE_SIZE = 50
    MAX_PAGES = 20          # cap list scan (Eightfold returns ~10/page)
    MAX_DETAILS = 150       # cap description fetches per company per run
    NAV_TIMEOUT = 60000     # ms
    CHALLENGE_WAIT = 5000   # ms to let the bot-challenge JS settle

    # A location is kept (and its description fetched) only if it looks North
    # American. Eightfold formats locations as "City,Region,Country".
    NA_MARKERS = ("canada", "united states", "usa", "u.s.")

    async def scrape_company(self, company: dict) -> list[RawJob]:
        host = (company.get("eightfold_host") or "").strip().rstrip("/")
        domain = (company.get("eightfold_domain") or "").strip()
        careers_url = (company.get("eightfold_careers_url")
                       or f"https://{host}/careers").strip()
        if not host or not domain:
            logger.warning(
                f"Eightfold/{company['company_name']}: missing eightfold_host/"
                f"eightfold_domain, skipping"
            )
            return []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "Eightfold/%s: playwright not installed; skipping. "
                "Add 'playwright' to requirements and run 'playwright install chromium'.",
                company["company_name"],
            )
            return []

        raw_jobs: list[RawJob] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                ctx = await browser.new_context(user_agent=_UA, locale="en-US")
                page = await ctx.new_page()
                try:
                    await page.goto(
                        careers_url, wait_until="domcontentloaded",
                        timeout=self.NAV_TIMEOUT,
                    )
                    await page.wait_for_timeout(self.CHALLENGE_WAIT)

                    positions = await self._collect_positions(page, host, domain)
                    na = [pos for pos in positions if self._is_na(pos)]
                    logger.info(
                        "Eightfold/%s: fetched %d positions, %d in North America",
                        company["company_name"], len(positions), len(na),
                    )

                    for i, pos in enumerate(na):
                        description = ""
                        if i < self.MAX_DETAILS:
                            description = await self._fetch_description(
                                page, host, domain, pos.get("id")
                            )
                        job = self._parse_job(pos, company, host, description)
                        if job:
                            raw_jobs.append(job)
                finally:
                    await browser.close()
        except Exception as e:
            logger.error(f"Eightfold/{company['company_name']}: scrape failed: {e}")
            return raw_jobs

        logger.info(f"Eightfold/{company['company_name']}: returning {len(raw_jobs)} jobs")
        return raw_jobs

    async def _page_fetch_json(self, page, url: str):
        """Fetch JSON from inside the authenticated page context."""
        result = await page.evaluate(
            """async (u) => {
                try {
                    const r = await fetch(u, {headers: {'Accept': 'application/json'}});
                    return {status: r.status, body: await r.text()};
                } catch (e) { return {status: -1, body: String(e)}; }
            }""",
            url,
        )
        if result.get("status") != 200:
            return None
        try:
            return json.loads(result["body"])
        except (json.JSONDecodeError, TypeError):
            return None

    async def _collect_positions(self, page, host: str, domain: str) -> list[dict]:
        positions: list[dict] = []
        offset = 0
        for _ in range(self.MAX_PAGES):
            url = (
                f"https://{host}/api/pcsx/search?domain={domain}&query=&location="
                f"&start={offset}&num={self.PAGE_SIZE}&sort_by=relevance"
            )
            payload = await self._page_fetch_json(page, url)
            if not payload:
                break
            data = payload.get("data") or {}
            batch = data.get("positions") or []
            if not batch:
                break
            positions.extend(batch)
            total = data.get("count", 0) or 0
            offset += len(batch)
            # Eightfold caps results per request, so don't stop just because a
            # page came back smaller than requested — advance by what we got and
            # stop only once we've covered the reported total (or hit an empty
            # page / the page cap).
            if total and offset >= total:
                break
        return positions

    async def _fetch_description(self, page, host: str, domain: str, pid) -> str:
        if not pid:
            return ""
        url = (
            f"https://{host}/api/pcsx/position_details?position_id={pid}"
            f"&domain={domain}&hl=en"
        )
        payload = await self._page_fetch_json(page, url)
        if not payload:
            return ""
        data = payload.get("data") or {}
        html = data.get("jobDescription") or ""
        if not html:
            return ""
        text = unescape(html)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) > 5000:
            text = text[:5000] + "..."
        return text

    @staticmethod
    def _location_text(pos: dict) -> str:
        locs = pos.get("locations")
        if isinstance(locs, list) and locs:
            return "; ".join(str(x) for x in locs if x)
        return pos.get("location") or ""

    def _is_na(self, pos: dict) -> bool:
        loc = self._location_text(pos).lower()
        return any(m in loc for m in self.NA_MARKERS)

    def _parse_posted_date(self, pos: dict) -> Optional[datetime]:
        ts = pos.get("postedTs") or pos.get("creationTs")
        if not ts:
            return None
        try:
            ts = float(ts)
            # Eightfold uses epoch seconds; tolerate ms.
            if ts > 1e12:
                ts /= 1000.0
            return datetime.utcfromtimestamp(ts)
        except (ValueError, TypeError, OSError):
            return None

    def _parse_job(
        self, pos: dict, company: dict, host: str, description: str
    ) -> Optional[RawJob]:
        try:
            title = pos.get("name") or pos.get("title") or ""
            pid = pos.get("id")
            if not title or not pid:
                return None

            url = (
                pos.get("publicUrl")
                or pos.get("positionUrl")
                or f"https://{host}/careers/job/{pid}"
            )
            # positionUrl/publicUrl may be a site-relative path.
            if url.startswith("/"):
                url = f"https://{host}{url}"
            elif not url.startswith("http"):
                url = f"https://{host}/careers/job/{pid}"

            department = pos.get("department") or ""
            if isinstance(department, list):
                department = department[0] if department else ""

            return RawJob(
                title=title,
                company=company["company_name"],
                location=self._location_text(pos),
                url=url,
                posted_date=self._parse_posted_date(pos),
                department=department,
                company_logo=company.get("company_logo_url", ""),
                company_url=company.get("company_url", ""),
                description=description,
            )
        except Exception as e:
            logger.warning(f"Error parsing Eightfold job: {e}")
            return None

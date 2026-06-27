"""
Logo + domain resolution for the standalone scraper.

Self-contained (no backend import) since this repo deploys independently.
Resolves a company to its registrable domain so the dashboard can render an
accurate logo and never show a broken image.

Priority:
1. A real company website URL (registry company_url, if present).
2. The domain encoded in the registry's company_logo_url favicon.
3. A curated known-company map.
4. A heuristic from the company name.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

_MULTI_PART_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.jp", "co.kr", "co.in", "co.nz", "co.za", "com.br", "com.mx",
    "com.sg", "com.hk", "com.tr",
}

_NON_COMPANY_HOSTS = {
    "jobright.ai", "newgrad-jobs.com", "linkedin.com", "indeed.com",
    "glassdoor.com", "github.com", "greenhouse.io", "lever.co",
    "myworkdayjobs.com", "ashbyhq.com", "smartrecruiters.com",
    "icims.com", "taleo.net", "bit.ly", "google.com",
}

KNOWN_DOMAINS: dict[str, str] = {
    "pwc": "pwc.com", "deloitte": "deloitte.com", "kpmg": "kpmg.com",
    "ey": "ey.com", "accenture": "accenture.com", "mckinsey": "mckinsey.com",
    "capgemini": "capgemini.com", "jp morgan": "jpmorgan.com",
    "jpmorgan": "jpmorgan.com", "goldman sachs": "goldmansachs.com",
    "td bank": "td.com", "td": "td.com", "rbc": "rbc.com",
    "royal bank": "rbc.com", "cibc": "cibc.com", "bmo": "bmo.com",
    "scotiabank": "scotiabank.com", "national bank": "nbc.ca",
    "manulife": "manulife.com", "sun life": "sunlife.com",
    "wealthsimple": "wealthsimple.com", "meta": "meta.com",
    "facebook": "meta.com", "google": "google.com", "alphabet": "google.com",
    "amazon": "amazon.com", "aws": "amazon.com", "electronic arts": "ea.com",
    "bytedance": "bytedance.com", "tiktok": "tiktok.com", "twitter": "x.com",
    "snap": "snap.com", "snapchat": "snap.com", "hewlett packard enterprise": "hpe.com",
    "databricks": "databricks.com", "snowflake": "snowflake.com",
    "datadog": "datadoghq.com", "mongodb": "mongodb.com",
    "cockroachdb": "cockroachlabs.com", "dbt labs": "getdbt.com",
    "elastic": "elastic.co", "confluent": "confluent.io", "neon": "neon.tech",
    "shopify": "shopify.com", "kinaxis": "kinaxis.com", "ciena": "ciena.com",
    "blackberry": "blackberry.com", "mitel": "mitel.com", "coveo": "coveo.com",
    "clio": "clio.com", "fullscript": "fullscript.com", "cgi": "cgi.com",
    "openai": "openai.com", "anthropic": "anthropic.com", "nvidia": "nvidia.com",
    "salesforce": "salesforce.com", "oracle": "oracle.com", "adobe": "adobe.com",
    "intuit": "intuit.com", "spotify": "spotify.com", "discord": "discord.com",
    "figma": "figma.com", "notion": "notion.so", "bloomberg": "bloomberg.com",
    "palantir": "palantir.com", "coinbase": "coinbase.com",
    "robinhood": "robinhood.com", "doordash": "doordash.com",
    "roblox": "roblox.com", "tesla": "tesla.com", "spacex": "spacex.com",
    "ericsson": "ericsson.com", "nokia": "nokia.com", "fortinet": "fortinet.com",
    "geotab": "geotab.com", "jobber": "getjobber.com", "1password": "1password.com",
    "benevity": "benevity.com", "trulioo": "trulioo.com", "klue": "klue.com",
    "loopio": "loopio.com", "thinkific": "thinkific.com", "hootsuite": "hootsuite.com",
    "neo financial": "neofinancial.com", "achievers": "achievers.com",
    "pointclickcare": "pointclickcare.com", "alayacare": "alayacare.com",
    "workleap": "workleap.com", "faire": "faire.com", "flipp": "flipp.com",
    "later": "later.com", "canonical": "canonical.com",
}

_NAME_NOISE = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|group|"
    r"holdings|technologies|technology|tech|solutions|solution|systems|labs|"
    r"laboratories|services|service|software|the|and|of)\b",
    re.IGNORECASE,
)

_LOGO_TEMPLATE = "https://www.google.com/s2/favicons?domain={domain}&sz=128"


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    last_two = ".".join(parts[-2:])
    last_three = ".".join(parts[-3:])
    return last_three if last_two in _MULTI_PART_TLDS else last_two


def domain_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    reg = _registrable(host)
    if reg in _NON_COMPANY_HOSTS or host in _NON_COMPANY_HOSTS:
        return None
    return reg


def domain_from_logo_url(logo_url: Optional[str]) -> Optional[str]:
    """Extract a domain embedded in a favicon/clearbit/icon.horse logo URL."""
    if not logo_url:
        return None
    m = re.search(r"[?&]domain=([^&]+)", logo_url)
    if m:
        return m.group(1)
    if "logo.clearbit.com/" in logo_url:
        return logo_url.split("logo.clearbit.com/")[1].split("?")[0] or None
    if "icon.horse/icon/" in logo_url:
        return logo_url.split("icon.horse/icon/")[1].split("?")[0] or None
    return None


def domain_from_name(company: Optional[str]) -> Optional[str]:
    if not company:
        return None
    normalized = _normalize_name(company)
    if not normalized:
        return None
    if normalized in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[normalized]
    token = re.sub(r"[^a-z0-9]", "", _NAME_NOISE.sub(" ", normalized))
    if len(token) < 2:
        token = re.sub(r"[^a-z0-9]", "", normalized)
    if len(token) < 2:
        return None
    return f"{token}.com"


def resolve_domain(
    company: Optional[str],
    company_url: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> Optional[str]:
    """Resolve the best company domain from the available signals."""
    return (
        domain_from_url(company_url)
        or domain_from_logo_url(logo_url)
        or domain_from_name(company)
    )


def logo_url_for_domain(domain: Optional[str]) -> str:
    return _LOGO_TEMPLATE.format(domain=domain) if domain else ""


def resolve_logo(
    company: Optional[str],
    company_url: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> tuple[str, str]:
    """Return (logo_url, domain); both "" when nothing resolves."""
    domain = resolve_domain(company, company_url, logo_url)
    # Prefer an existing real logo URL if it's not a generated favicon/clearbit.
    if logo_url and logo_url.startswith("http") and not any(
        k in logo_url for k in ("google.com/s2", "clearbit", "icon.horse", "apistemic", "hunter.io")
    ):
        return logo_url, (domain or "")
    return logo_url_for_domain(domain), (domain or "")

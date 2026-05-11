"""Database connection and job storage for the ATS scraper.

Connects directly to the Neon PostgreSQL database and writes ScrapedJob records.
Uses INSERT ... ON CONFLICT (url) DO NOTHING for deduplication.
"""

import ssl
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qs

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, Enum, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class ScrapedJob(Base):
    """Mirror of the backend ScrapedJob model — fields the scraper writes."""
    __tablename__ = "scraped_jobs"

    id = Column(Integer, primary_key=True)
    platform = Column(String, default="greenhouse")
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, default="")
    url = Column(String, nullable=False, unique=True)
    description = Column(Text, default="")
    easy_apply = Column(Integer, default=0)
    status = Column(Enum("new", "applying", "waiting_answer", "applied", "failed", "skipped", name="jobstatus"), default="new")
    scraped_at = Column(DateTime, default=datetime.utcnow)
    posted_date = Column(DateTime, nullable=True)
    match_score = Column(Integer, default=0)
    requirements_met = Column(Integer, default=0)
    requirements_total = Column(Integer, default=0)
    match_summary = Column(Text, default="")
    requirements_detail = Column(JSON, default=list)
    salary_range = Column(String, default="")
    company_size = Column(String, default="")
    company_description = Column(Text, default="")
    company_logo = Column(String, default="")
    ats_type = Column(String, default="")
    experience_years_required = Column(Integer, nullable=True)
    skip_reason = Column(String, default="")
    source_platform = Column(String, default="ats")
    saved = Column(Integer, default=0)
    experience_score = Column(Integer, default=0)
    skill_score = Column(Integer, default=0)
    industry_score = Column(Integer, default=0)
    match_label = Column(String, default="")
    applicant_count = Column(Integer, nullable=True)
    github_source_id = Column(Integer, nullable=True)
    last_viewed_at = Column(DateTime, nullable=True)
    work_type = Column(String, default="onsite")
    role_category = Column(String, default="")
    country = Column(String, default="")
    experience_level = Column(String, default="")


def get_engine(database_url: str):
    """Create SQLAlchemy engine with proper SSL for Neon PostgreSQL."""
    # Rewrite URL for pg8000 driver
    url = database_url.split("?")[0]  # strip query params
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+pg8000://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)

    ssl_context = ssl.create_default_context()
    engine = create_engine(url, connect_args={"ssl_context": ssl_context}, pool_pre_ping=True)
    return engine


def get_session(database_url: str):
    """Create a database session."""
    engine = get_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication.

    - Strip trailing slashes
    - Sort query parameters
    - Remove common tracking params (utm_source, utm_campaign, etc.)
    """
    if not url:
        return url

    parsed = urlparse(url.strip())

    # Remove trailing slash from path
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

    # Parse and sort query params, removing tracking params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {k: v for k, v in sorted(params.items()) if k.lower() not in tracking_params}

    # Rebuild query string
    query = urlencode(filtered_params, doseq=True) if filtered_params else ""

    # Rebuild URL
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if query:
        normalized += f"?{query}"

    return normalized


def store_job(session, job_data: dict) -> bool:
    """Insert a job record. Returns True if inserted, False if duplicate.

    Uses a check-then-insert approach with exception handling for race conditions.
    """
    url = normalize_url(job_data.get("url", ""))
    if not url:
        return False

    # Check if URL already exists
    existing = session.query(ScrapedJob).filter(ScrapedJob.url == url).first()
    if existing:
        return False

    # Create and insert the job
    job = ScrapedJob(
        platform=job_data.get("platform", "greenhouse"),
        title=job_data.get("title", ""),
        company=job_data.get("company", ""),
        location=job_data.get("location", ""),
        url=url,
        description=job_data.get("description", ""),
        posted_date=job_data.get("posted_date"),
        salary_range=job_data.get("salary_range", ""),
        company_logo=job_data.get("company_logo", ""),
        ats_type=job_data.get("ats_type", ""),
        source_platform="ats",
        work_type=job_data.get("work_type", "onsite"),
        role_category=job_data.get("role_category", ""),
        country=job_data.get("country", ""),
        experience_level=job_data.get("experience_level", ""),
    )
    session.add(job)
    try:
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False

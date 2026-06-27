"""Company registry loader and validator."""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"company_name", "ats_platform", "board_slug"}
VALID_PLATFORMS = {"greenhouse", "lever", "ashby", "workday", "oracle"}


def load_registry(path: Optional[str] = None) -> list[dict]:
    """Load and validate company registry from JSON file.
    
    Returns list of valid, enabled company entries.
    Logs warnings for invalid entries and skips them.
    """
    if path is None:
        path = str(Path(__file__).parent / "companies.json")
    
    with open(path, "r") as f:
        data = json.load(f)
    
    companies = data.get("companies", [])
    valid = []
    
    for i, entry in enumerate(companies):
        # Check required fields
        missing = REQUIRED_FIELDS - set(entry.keys())
        if missing:
            logger.warning(f"Company entry {i} missing fields {missing}, skipping: {entry.get('company_name', 'unknown')}")
            continue
        
        # Validate platform
        if entry["ats_platform"] not in VALID_PLATFORMS:
            logger.warning(f"Company entry {i} has invalid platform '{entry['ats_platform']}', skipping: {entry['company_name']}")
            continue
        
        # Check enabled flag (default True if absent)
        if not entry.get("enabled", True):
            continue
        
        valid.append(entry)
    
    return valid


def group_by_platform(companies: list[dict]) -> dict[str, list[dict]]:
    """Group companies by their ATS platform."""
    groups: dict[str, list[dict]] = {}
    for company in companies:
        platform = company["ats_platform"]
        if platform not in groups:
            groups[platform] = []
        groups[platform].append(company)
    return groups

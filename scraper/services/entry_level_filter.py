"""Filters jobs to entry-level positions only (intern, new grad, junior)."""

import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class FilterResult:
    """Result of entry-level filtering."""
    is_entry_level: bool
    experience_level: Optional[str] = None  # "internship" or "new_grad"


class EntryLevelFilter:
    """Identifies entry-level positions by analyzing job titles."""
    
    INTERN_PATTERNS = [
        re.compile(r"\bintern\b", re.IGNORECASE),
        re.compile(r"\binternship\b", re.IGNORECASE),
        re.compile(r"\bco-?op\b", re.IGNORECASE),
    ]
    
    NEW_GRAD_PATTERNS = [
        re.compile(r"\bnew\s+grad(?:uate)?\b", re.IGNORECASE),
        re.compile(r"\bentry[\s-]level\b", re.IGNORECASE),
        re.compile(r"\bjunior\b", re.IGNORECASE),
        re.compile(r"\bassociate\b", re.IGNORECASE),
        re.compile(r"\b0-2\s+years?\b", re.IGNORECASE),
        re.compile(r"\bearly\s+career\b", re.IGNORECASE),
        re.compile(r"\buniversity\b", re.IGNORECASE),
        re.compile(r"\s+I$"),  # Roman numeral suffix at end of title
        re.compile(r"\s+I\b(?![A-Za-z])"),  # "I" as standalone suffix
    ]
    
    SENIOR_EXCLUSIONS = [
        re.compile(r"\bsenior\b", re.IGNORECASE),
        re.compile(r"\bstaff\b", re.IGNORECASE),
        re.compile(r"\bprincipal\b", re.IGNORECASE),
        re.compile(r"\blead\b", re.IGNORECASE),
        re.compile(r"\bmanager\b", re.IGNORECASE),
        re.compile(r"\bdirector\b", re.IGNORECASE),
        re.compile(r"\bvp\b", re.IGNORECASE),
        re.compile(r"\bhead\s+of\b", re.IGNORECASE),
    ]
    
    def filter(self, title: str) -> FilterResult:
        """Evaluate a job title for entry-level indicators.
        
        Logic:
        1. If title has senior indicators → exclude
        2. If title has intern indicators → internship
        3. If title has new grad indicators → new_grad
        4. If title has NO seniority indicator at all → new_grad (assume entry-level)
        """
        if not title:
            return FilterResult(is_entry_level=False)
        
        # Check for senior-level exclusions first
        for pattern in self.SENIOR_EXCLUSIONS:
            if pattern.search(title):
                return FilterResult(is_entry_level=False)
        
        # Check intern patterns
        for pattern in self.INTERN_PATTERNS:
            if pattern.search(title):
                return FilterResult(is_entry_level=True, experience_level="internship")
        
        # Check new grad patterns
        for pattern in self.NEW_GRAD_PATTERNS:
            if pattern.search(title):
                return FilterResult(is_entry_level=True, experience_level="new_grad")
        
        # No seniority indicator at all — include as new_grad
        # (Most entry-level jobs are just "Software Engineer", "Data Analyst", etc.)
        return FilterResult(is_entry_level=True, experience_level="new_grad")

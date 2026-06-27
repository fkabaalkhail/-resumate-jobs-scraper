"""Filters jobs to US and Canada only, extracts work_type and country."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class LocationResult:
    """Result of location filtering."""
    is_included: bool
    country: str = ""       # "US" or "CA"
    work_type: str = ""     # "remote", "hybrid", "onsite"


class LocationFilter:
    """Filters jobs to US/Canada and extracts work arrangement type."""
    
    US_STATE_ABBREVS = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    }
    
    US_STATE_NAMES = {
        "alabama", "alaska", "arizona", "arkansas", "california",
        "colorado", "connecticut", "delaware", "florida", "georgia",
        "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
        "kentucky", "louisiana", "maine", "maryland", "massachusetts",
        "michigan", "minnesota", "mississippi", "missouri", "montana",
        "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
        "new york", "north carolina", "north dakota", "ohio", "oklahoma",
        "oregon", "pennsylvania", "rhode island", "south carolina",
        "south dakota", "tennessee", "texas", "utah", "vermont",
        "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    }
    
    CA_PROVINCE_ABBREVS = {"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "NT", "YT", "NU"}
    
    CA_PROVINCE_NAMES = {
        "ontario", "quebec", "british columbia", "alberta", "manitoba",
        "saskatchewan", "nova scotia", "new brunswick",
        "newfoundland", "prince edward island",
    }
    
    US_INDICATORS = {"united states", "usa", "u.s.", "u.s.a."}
    CA_INDICATORS = {"canada", "can"}

    # Bare city names some ATS platforms emit without province/country.
    CA_CITIES = {
        "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary",
        "edmonton", "winnipeg", "hamilton", "kitchener", "waterloo",
        "mississauga", "brampton", "markham", "london", "victoria", "halifax",
        "burnaby", "richmond", "gatineau", "kanata", "scarborough",
        "north york", "etobicoke", "vaughan", "oakville", "burlington",
        "guelph", "saskatoon", "regina", "fredericton", "moncton", "kelowna",
        "windsor", "laval", "longueuil", "sherbrooke", "barrie", "nepean",
    }
    US_CITIES = {
        "new york", "san francisco", "los angeles", "chicago", "seattle",
        "austin", "boston", "denver", "atlanta", "dallas", "houston",
        "miami", "philadelphia", "phoenix", "san diego", "san jose",
        "portland", "minneapolis", "detroit", "pittsburgh", "raleigh",
        "charlotte", "nashville", "mountain view", "palo alto", "sunnyvale",
        "cupertino", "menlo park", "redmond", "bellevue", "irvine",
        "santa monica", "brooklyn", "manhattan",
    }
    
    def filter(self, location: str) -> LocationResult:
        """Evaluate location for country and work type."""
        if not location:
            return LocationResult(is_included=False)
        
        work_type = self._classify_work_type(location)
        country = self._classify_country(location)
        
        if country:
            return LocationResult(is_included=True, country=country, work_type=work_type)
        
        return LocationResult(is_included=False)
    
    def _classify_country(self, location: str) -> Optional[str]:
        """Classify location into 'US', 'CA', or None."""
        loc_lower = location.lower()
        
        # Emoji flags
        if "\U0001f1fa\U0001f1f8" in location:  # 🇺🇸
            return "US"
        if "\U0001f1e8\U0001f1e6" in location:  # 🇨🇦
            return "CA"
        
        # Explicit country indicators
        for indicator in self.CA_INDICATORS:
            if indicator in loc_lower:
                return "CA"
        
        for indicator in self.US_INDICATORS:
            if indicator in loc_lower:
                return "US"
        
        # Province abbreviations (check Canada first for non-ambiguous ones)
        city_region = re.search(r'[A-Za-z\s]+,\s*([A-Z]{2})\b', location)
        if city_region:
            abbrev = city_region.group(1)
            if abbrev in self.CA_PROVINCE_ABBREVS and abbrev not in self.US_STATE_ABBREVS:
                return "CA"
            if abbrev in self.US_STATE_ABBREVS:
                return "US"
        
        # Province names
        for province in self.CA_PROVINCE_NAMES:
            if province in loc_lower:
                return "CA"
        
        # State names
        for state in self.US_STATE_NAMES:
            if state in loc_lower:
                return "US"

        # Standalone state abbreviations
        tokens = re.findall(r'\b([A-Z]{2})\b', location)
        for token in tokens:
            if token in self.US_STATE_ABBREVS:
                return "US"
            if token in self.CA_PROVINCE_ABBREVS:
                return "CA"

        # Bare city names (some ATS, e.g. Workday, give just "Ottawa").
        # Use word-boundary matching to avoid substring false positives.
        for city in self.CA_CITIES:
            if re.search(rf'\b{re.escape(city)}\b', loc_lower):
                return "CA"
        for city in self.US_CITIES:
            if re.search(rf'\b{re.escape(city)}\b', loc_lower):
                return "US"

        # "Remote" without country defaults to US
        if re.search(r'\bremote\b', loc_lower):
            return "US"
        
        # "Hybrid" or "In-Office" without any location info — default to US
        # (Most companies using these ATS platforms are US-based)
        if re.search(r'\b(hybrid|in-?office|on-?site|onsite)\b', loc_lower):
            return "US"
        
        return None
    
    def _classify_work_type(self, location: str) -> str:
        """Classify location into 'remote', 'hybrid', or 'onsite'."""
        loc_lower = location.lower()
        
        if re.search(r'\bremote\b', loc_lower):
            return "remote"
        if re.search(r'\bhybrid\b', loc_lower):
            return "hybrid"
        
        return "onsite"

"""Classifies jobs into canonical role categories based on title/department.

This MUST stay in sync with backend/services/role_classifier.py so that jobs
scraped here land in the same categories the dashboard filter exposes.
"""


# Canonical category names (the order the frontend shows them in).
CANONICAL_CATEGORIES = [
    "Software Engineering",
    "Engineering and Development",
    "Data Analysis",
    "Machine Learning and AI",
    "Accounting and Finance",
    "Management and Executive",
    "Sales",
    "Marketing",
    "Human Resources",
    "Product Management",
    "Business Analyst",
    "Creatives and Design",
    "Legal and Compliance",
    "Customer Service and Support",
    "Operations",
    "Consultant",
    "Other",
]

# Ordered (category, keywords). First keyword hit wins, so specific categories
# come before broader ones.
_KEYWORD_GROUPS = [
    ("Machine Learning and AI", [
        "machine learning", "ml engineer", "ml scientist", "ai engineer",
        "ai/ml", "ml/ai", "ai & ml", " ml ", "ml intern", "artificial intelligence",
        "deep learning", "nlp", "natural language", "computer vision",
        "data scientist", "research scientist", "applied scientist",
        "applied science", "generative ai", " llm", "ai agent", "ai intern",
        "ai developer", "ai data", "ai research",
    ]),
    ("Data Analysis", [
        "data analyst", "data analysis", "data analytics", "business intelligence",
        "bi analyst", "bi developer", "analytics", "data engineer",
        "data warehouse", "data science", "quantitative analyst",
        "reporting analyst", "data governance", "data quality",
        "data and business intelligence",
    ]),
    ("Software Engineering", [
        "software", "developer", "swe", " sde", "full stack", "fullstack",
        "full-stack", "back end", "backend", "front end", "frontend",
        "web developer", "mobile developer", "ios developer",
        "android developer", "programmer", "applications engineer",
        "application developer", ".net", "java developer", "python developer",
    ]),
    ("Engineering and Development", [
        "mechanical engineer", "electrical engineer", "civil engineer",
        "hardware", "firmware", "embedded", "fpga", "asic", "rf engineer",
        "optical", "photonics", "validation", "manufacturing engineer",
        "process engineer", "systems engineer", "network engineer",
        "devops", "site reliability", "sre", "infrastructure",
        "platform engineer", "cloud engineer", "security engineer",
        "cybersecurity", "qa engineer", "quality engineer", "test engineer",
        "quality assurance", "qa ", "automation engineer", "controls engineer",
        "industrial engineer", "chemical engineer", "aerospace engineer",
        "structural engineer", "engineer", "engineering", "technician",
    ]),
    ("Management and Executive", [
        "chief", " ceo ", " cfo ", " coo ", " cto ", " ciso ",
        "vice president", " vp ", "executive director", "managing director",
        "general manager", "head of",
    ]),
    ("Accounting and Finance", [
        "accountant", "accounting", "finance", "financial", "audit",
        "auditor", "tax", "treasury", "controller", "bookkeep", "payroll",
        "fp&a", "investment", "actuarial", "mergers", "mergers and acquisitions",
        "m&a", "private equity", "venture capital", "private client", "wealth",
        "asset management", "capital markets", "assurance", "underwriting",
        "financial reporting",
    ]),
    ("Sales", [
        "sales", "account executive", "account manager", "bdr", "sdr",
        "business development", "account representative", "inside sales",
        "sales development", "sales enablement", "partner enablement",
        "customer development", "account services", "field sales",
    ]),
    ("Marketing", [
        "marketing", "growth", "seo", "sem", "brand", "communications",
        "social media", "content strategist", "content marketing",
        "content creation", "content management", "public relations",
        "publicity", "demand generation", "copywriter",
    ]),
    ("Human Resources", [
        "human resources", "recruiter", "recruiting", "talent acquisition",
        "people operations", "people & culture", "people and culture",
        "hr ", "hris", "compensation", "organizational development",
        "organizational learning", "talent development", "employee experience",
        "talent and culture", "talent et culture", "change management",
    ]),
    ("Product Management", [
        "product manager", "product owner", "program manager",
        "technical program", "product management", "project manager",
    ]),
    ("Business Analyst", [
        "business analyst", "strategy analyst", "business systems analyst",
    ]),
    ("Creatives and Design", [
        "designer", "ux", "ui ", " ui", "graphic", "visual design",
        "product design", "interaction design", "creative", "illustrator",
        "animator", "artist", "video editor",
    ]),
    ("Legal and Compliance", [
        "legal", "counsel", "attorney", "paralegal", "compliance",
        "regulatory", "lawyer",
    ]),
    ("Customer Service and Support", [
        "customer support", "customer success", "customer service",
        "support engineer", "technical support", "help desk", "service desk",
        "client support",
    ]),
    ("Operations", [
        "operations", "supply chain", "logistics", "procurement",
        "project coordinator", "warehouse", "fulfillment", "inventory",
        "buyer", "planner",
    ]),
    ("Consultant", [
        "consultant", "consulting", "advisory",
    ]),
]


class CategoryClassifier:
    """Assigns a canonical role_category based on job title and department."""

    def classify(self, title: str, department: str = "") -> str:
        title_lower = f" {(title or '').lower()} "
        for category, keywords in _KEYWORD_GROUPS:
            for kw in keywords:
                if kw in title_lower:
                    return category

        dept = (department or "").strip()
        if dept:
            dept_lower = f" {dept.lower()} "
            for category, keywords in _KEYWORD_GROUPS:
                for kw in keywords:
                    if kw in dept_lower:
                        return category

        return "Other"

"""Classifies jobs into role categories based on title and department keywords."""

import re


class CategoryClassifier:
    """Assigns role_category based on job title and department metadata."""
    
    CATEGORIES: dict[str, list[str]] = {
        "Software Engineering": [
            "software", "developer", "swe", "full stack", "fullstack",
            "backend", "frontend", "full-stack", "web developer",
            "mobile developer", "ios developer", "android developer",
            "engineer", "engineering",
        ],
        "Data Analysis": [
            "data analyst", "business intelligence", "bi analyst",
            "analytics", "data science", "data engineer",
        ],
        "Machine Learning/AI": [
            "machine learning", "ml engineer", "ai engineer",
            "artificial intelligence", "deep learning", "nlp",
            "computer vision", "research scientist",
        ],
        "Product Management": [
            "product manager", "program manager", "technical program",
            "product owner",
        ],
        "Marketing": [
            "marketing", "growth", "content", "seo", "sem",
            "brand", "communications",
        ],
        "Design": [
            "designer", "ux", "ui", "graphic", "visual design",
            "product design", "interaction design",
        ],
        "Business Analyst": ["business analyst", "strategy analyst"],
        "Accounting/Finance": [
            "accountant", "finance", "financial analyst",
            "accounting", "audit", "tax",
        ],
        "Sales": [
            "sales", "account executive", "bdr", "sdr",
            "business development",
        ],
        "Human Resources": [
            "human resources", "hr ", "recruiter", "talent",
            "people operations",
        ],
        "Legal": ["legal", "counsel", "attorney", "compliance", "paralegal"],
        "Operations": [
            "operations", "supply chain", "logistics",
            "procurement", "project coordinator",
        ],
        "Customer Support": [
            "customer support", "customer success", "support engineer",
            "technical support", "help desk",
        ],
        "Hardware Engineering": [
            "hardware", "electrical engineer", "mechanical engineer",
            "embedded", "firmware",
        ],
        "Cybersecurity": [
            "security", "cybersecurity", "infosec",
            "penetration", "security engineer",
        ],
        "DevOps/Infrastructure": [
            "devops", "sre", "infrastructure", "platform engineer",
            "cloud engineer", "site reliability",
        ],
    }
    
    def classify(self, title: str, department: str = "") -> str:
        """Classify a job into a role category.
        
        Priority: title keywords > department keywords > "Other"
        """
        title_lower = title.lower()
        
        # Try title-based classification first
        for category, keywords in self.CATEGORIES.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return category
        
        # Fallback to department-based classification
        if department:
            dept_lower = department.lower()
            for category, keywords in self.CATEGORIES.items():
                for keyword in keywords:
                    if keyword in dept_lower:
                        return category
        
        return "Other"

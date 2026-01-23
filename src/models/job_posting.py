"""Pydantic model for standardized job postings."""

import hashlib
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JobPosting(BaseModel):
    """Standardized job posting model used across all fetchers."""

    # Source
    source: str
    source_url: str

    # Company
    company: str
    company_url: Optional[str] = None

    # Job details
    title: str
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    job_type: Optional[Literal["Full-time", "Part-time", "Contract", "Internship"]] = None

    # Compensation (in cents to avoid float issues)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    salary_source: Optional[Literal["direct", "parsed", "not_listed"]] = "not_listed"

    # Content
    description: str = ""
    requirements: str = ""

    # Dates
    posted_date: Optional[str] = None

    # Raw data
    raw_data: dict = Field(default_factory=dict)

    @property
    def job_hash(self) -> str:
        """Generate unique hash for deduplication.

        Based on company + title + first 500 chars of description.
        """
        unique_string = f"{self.company.lower()}|{self.title.lower()}|{self.description[:500]}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    @model_validator(mode="after")
    def detect_remote(self):
        """Auto-detect remote from location if not explicitly set."""
        if self.is_remote is None and self.location:
            location = self.location.lower()
            remote_keywords = ["remote", "anywhere", "work from home", "wfh", "distributed"]
            self.is_remote = any(keyword in location for keyword in remote_keywords)
        return self

    @field_validator("job_type", mode="before")
    @classmethod
    def normalize_job_type(cls, v):
        """Normalize job type to standard values."""
        if v is None:
            return None

        v_lower = v.lower().strip()

        if "full" in v_lower or v_lower == "ft":
            return "Full-time"
        elif "part" in v_lower or v_lower == "pt":
            return "Part-time"
        elif "contract" in v_lower or "freelance" in v_lower:
            return "Contract"
        elif "intern" in v_lower:
            return "Internship"

        return None  # Unknown type

    def to_db_dict(self) -> dict:
        """Convert to database-compatible dict."""
        return {
            "job_hash": self.job_hash,
            "source": self.source,
            "source_url": self.source_url,
            "company": self.company,
            "company_url": self.company_url,
            "title": self.title,
            "location": self.location,
            "is_remote": self.is_remote,
            "job_type": self.job_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "salary_source": self.salary_source,
            "description": self.description,
            "requirements": self.requirements,
            "posted_date": self.posted_date,
            "raw_data": json.dumps(self.raw_data),
        }

    model_config = ConfigDict(extra="ignore")  # Ignore extra fields from raw data

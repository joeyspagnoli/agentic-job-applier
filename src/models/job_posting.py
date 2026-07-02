"""Define the normalized job-posting model used across the repository.

This module turns fetcher-specific payloads into a shared shape that the
database layer, deduplicator, and agent pipeline can all rely on.
"""

import hashlib
import json
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def map_job_type(
    v: str | None,
) -> Literal["Full-time", "Part-time", "Contract", "Internship"] | None:
    """Map raw job-type strings to canonical Literal values.

    Purpose:
        Collapse varied job-type strings from different sources into a small
        canonical set.  Used by the ``normalize_job_type`` field validator and
        by fetchers that need to produce a typed value before constructing a
        ``JobPosting``.
    Args:
        v: Raw incoming job-type value, or ``None``.
    Output:
        Returns the normalized job-type string or ``None`` when the value does
        not map cleanly to one of the supported categories.
    """
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
    return None


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

    # Raw data - typed as dict[str, object] to accept any dict-like source payload;
    # Pydantic serializes this correctly at runtime via json.dumps in to_db_dict.
    raw_data: dict[str, object] = Field(default_factory=dict)

    @property
    def job_hash(self) -> str:
        """Generate the stable hash used for deduplication.

        Purpose:
            Create a reproducible identifier with enough entropy to avoid
            collapsing distinct jobs that share generic boilerplate text.
        Args:
            self: The normalized job posting whose identifying content is hashed.
        Output:
            Returns a SHA-256 hex digest derived from canonicalized identity
            fields and full-content digests.
        """

        # URL query parameters frequently include tracking data, so URL identity
        # is normalized before being included in the dedup fingerprint.
        identity_parts = [
            self.company.lower().strip(),
            self.title.lower().strip(),
            self._normalize_text(self.location),
            self._normalize_text(self.posted_date),
            self._canonicalize_url(self.source_url),
            hashlib.sha256(self._normalize_text(self.description).encode()).hexdigest(),
            hashlib.sha256(self._normalize_text(self.requirements).encode()).hexdigest(),
        ]
        return hashlib.sha256("|".join(identity_parts).encode()).hexdigest()

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        """Normalize optional text into a stable, comparable representation.

        Purpose:
            Collapse casing and whitespace differences so hash inputs stay
            stable across minor formatting changes in source payloads.
        Args:
            value: Optional text value that should be normalized.
        Output:
            Returns lowercased text with internal whitespace collapsed.
        """

        if not value:
            return ""
        return " ".join(str(value).lower().split())

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        """Canonicalize source URLs before deduplication hashing.

        Purpose:
            Avoid hash churn from query-param order and common tracking params
            while preserving the URL components that identify the posting.
        Args:
            url: Raw source URL from a fetcher payload.
        Output:
            Returns a normalized URL string used in the hash identity fields.
        """

        if not url:
            return ""

        parts = urlsplit(url.strip())
        query_items = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            key_lower = key.lower()
            if key_lower.startswith("utm_") or key_lower in {"gh_src", "gh_jid"}:
                continue
            query_items.append((key, value))

        normalized_query = urlencode(sorted(query_items))
        normalized_parts = (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            normalized_query,
            "",
        )
        return urlunsplit(normalized_parts)

    @model_validator(mode="after")
    def detect_remote(self) -> "JobPosting":
        """Infer the remote flag from the location text when needed.

        Purpose:
            Normalize a common fetcher gap where remote status is implied in the
            location string rather than provided as a dedicated field.
        Args:
            self: The partially validated model instance being finalized.
        Output:
            Returns the model instance after filling `is_remote` when the
            location text clearly signals remote work.
        """

        # Fetchers often pass through raw location strings, so this validator
        # centralizes the remote-detection heuristic in one place.
        if self.is_remote is None and self.location:
            location = self.location.lower()
            remote_keywords = ["remote", "anywhere", "work from home", "wfh", "distributed"]
            self.is_remote = any(keyword in location for keyword in remote_keywords)
        return self

    @field_validator("job_type", mode="before")
    @classmethod
    def normalize_job_type(
        cls,
        v: str | None,
    ) -> Literal["Full-time", "Part-time", "Contract", "Internship"] | None:
        """Normalize source-specific job-type labels to the shared enum set.

        Purpose:
            Collapse varied job-type strings from different sources into a small
            canonical set before the record is stored or analyzed.
        Args:
            cls: The Pydantic model class invoking the validator.
            v: Raw incoming job-type value from a fetcher payload.
        Output:
            Returns the normalized job-type string or `None` when the value does
            not map cleanly to one of the supported categories.
        """
        return map_job_type(v)

    def to_db_dict(self) -> dict[str, object]:
        """Convert the model into a database-ready dictionary payload.

        Purpose:
            Bridge the in-memory Pydantic model and the SQLite insert statement
            expected by `DatabaseManager.insert_job`.
        Args:
            self: The normalized job posting being prepared for persistence.
        Output:
            Returns a dictionary whose keys match the `job_postings` insert
            placeholders, including JSON serialization of raw source data.
        """

        # Raw source payloads are serialized here so the database layer can stay
        # focused on SQL concerns instead of model-specific conversions.
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

    # Extra keys are ignored so fetchers can pass through heterogeneous payloads
    # without updating the model every time a source adds a new field.
    model_config = ConfigDict(extra="ignore")

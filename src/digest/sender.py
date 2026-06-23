"""Send a daily digest email to every confirmed subscriber.

Queries job_postings for roles fetched since each subscriber's last
digest, filters by their stored preferences, renders an HTML email, and
delivers it via the Resend API.  On success it writes digest_sends rows
and bumps last_digest_at.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite
import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RESEND_URL = "https://api.resend.com/emails"

# How far back to look when a subscriber has never received a digest.
_DEFAULT_LOOKBACK_HOURS = 24

# Resend rate-limit courtesy pause between subscribers.
_INTER_SEND_DELAY_SECONDS = 0.2

# HTTP request timeout for the Resend API.
_RESEND_TIMEOUT_SECONDS = 10.0

# Intern / co-op role patterns (case-insensitive substring match).
_INTERN_TITLE_PATTERNS: tuple[str, ...] = ("intern", "co-op", "coop", "student")

# New-grad / early-career role patterns (case-insensitive substring match).
_NEW_GRAD_TITLE_PATTERNS: tuple[str, ...] = (
    "new grad",
    "new-grad",
    "early career",
    "early-career",
    "junior",
    "entry level",
    "entry-level",
)

# Maps subscriber field IDs to SimplifyJobs category strings stored in raw_data.
_FIELD_TO_CATEGORY: dict[str, str] = {
    "software": "Software",
    "ai_ml_data": "AI/ML/Data",
    "hardware": "Hardware",
    "product": "Product",
    "quant": "Quant",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_daily_digest(
    db_path: str,
    resend_api_key: str,
    from_address: str,
    base_url: str = "",
) -> dict[str, int]:
    """Send the daily job digest to every confirmed subscriber.

    Args:
        db_path: Filesystem path to the SQLite database file.
        resend_api_key: Bearer token for the Resend email API.
        from_address: The ``From:`` address used in outgoing emails.
        base_url: Origin prefix for links in emails
            (e.g. ``https://jobs.cloud.joeyspagnoli-cloud.cc``).
            Defaults to empty string for relative URLs in local dev.
    """
    totals: dict[str, int] = {"total_subscribers": 0, "emails_sent": 0, "errors": 0}

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        subscribers = await _fetch_confirmed_subscribers(db)
        totals["total_subscribers"] = len(subscribers)

        for subscriber in subscribers:
            success = await _process_subscriber(
                db=db,
                subscriber=subscriber,
                resend_api_key=resend_api_key,
                from_address=from_address,
                base_url=base_url,
            )
            if success:
                totals["emails_sent"] += 1
            elif success is False:
                totals["errors"] += 1

            await asyncio.sleep(_INTER_SEND_DELAY_SECONDS)

    return totals


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def _fetch_confirmed_subscribers(
    db: aiosqlite.Connection,
) -> list[aiosqlite.Row]:
    """Return all rows from email_subscribers where confirmed=1."""
    cursor = await db.execute(
        "SELECT * FROM email_subscribers WHERE confirmed = 1"
    )
    return await cursor.fetchall()


async def _fetch_new_jobs_for_subscriber(
    db: aiosqlite.Connection,
    since_iso: str,
) -> list[aiosqlite.Row]:
    """Return job postings fetched after since_iso."""
    cursor = await db.execute(
        "SELECT * FROM job_postings WHERE fetched_at > ?",
        (since_iso,),
    )
    return await cursor.fetchall()


async def _record_digest_sends(
    db: aiosqlite.Connection,
    subscriber_id: int,
    job_ids: list[int],
    sent_at_iso: str,
) -> None:
    """Insert digest_sends rows and update last_digest_at."""
    await db.executemany(
        "INSERT INTO digest_sends (subscriber_id, job_id, sent_at) VALUES (?, ?, ?)",
        [(subscriber_id, job_id, sent_at_iso) for job_id in job_ids],
    )
    await db.execute(
        "UPDATE email_subscribers SET last_digest_at = ? WHERE id = ?",
        (sent_at_iso, subscriber_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Per-subscriber processing
# ---------------------------------------------------------------------------


async def _process_subscriber(
    db: aiosqlite.Connection,
    subscriber: aiosqlite.Row,
    resend_api_key: str,
    from_address: str,
    base_url: str = "",
) -> bool | None:
    since_iso = _resolve_lookback_cutoff(subscriber["last_digest_at"])
    raw_jobs = await _fetch_new_jobs_for_subscriber(db, since_iso)

    if not raw_jobs:
        return None

    preferences = _parse_subscriber_preferences(subscriber)
    filtered = _apply_preference_filters(raw_jobs, preferences)

    if not filtered:
        return None

    deduped = _dedup_by_company_title(filtered)
    grouped = _group_by_category(deduped)
    subject, html_body = _render_email(
        jobs_by_category=grouped,
        unsubscribe_token=subscriber["unsubscribe_token"],
        base_url=base_url,
    )

    sent_at_iso = datetime.now(tz=timezone.utc).isoformat()

    try:
        await _send_via_resend(
            resend_api_key=resend_api_key,
            from_address=from_address,
            to_address=subscriber["email"],
            subject=subject,
            html_body=html_body,
        )
    except httpx.HTTPError as exc:
        logger.error(
            "Resend delivery failed for subscriber {}: {}",
            subscriber["id"],
            exc,
        )
        return False

    job_ids = [job["id"] for job in deduped]
    await _record_digest_sends(db, subscriber["id"], job_ids, sent_at_iso)

    logger.info(
        "Digest sent to subscriber {} ({} jobs)",
        subscriber["id"],
        len(job_ids),
    )
    return True


# ---------------------------------------------------------------------------
# Preference parsing and filtering
# ---------------------------------------------------------------------------


def _resolve_lookback_cutoff(last_digest_at: str | None) -> str:
    """Return an ISO timestamp to use as the lower bound for job queries."""
    if last_digest_at:
        return last_digest_at

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_DEFAULT_LOOKBACK_HOURS)
    return cutoff.isoformat()


def _parse_subscriber_preferences(subscriber: aiosqlite.Row) -> dict[str, Any]:
    """Decode JSON fields and normalise preference values from a subscriber row.

    Args:
        subscriber: Raw row from email_subscribers.

    Returns:
        Dict with keys: role_level, allowed_categories, location_preference,
        excluded_companies_lower.
    """
    raw_fields: str | None = subscriber["fields"]
    field_ids: list[str] = json.loads(raw_fields) if raw_fields else []
    allowed_categories = {_FIELD_TO_CATEGORY[f] for f in field_ids if f in _FIELD_TO_CATEGORY}

    raw_terms: str | None = subscriber["terms"]
    allowed_terms = set(json.loads(raw_terms)) if raw_terms else set()

    raw_excluded: str = subscriber["excluded_companies"] or "[]"
    excluded_companies_lower = {c.lower() for c in json.loads(raw_excluded)}

    return {
        "role_level": subscriber["role_level"],
        "allowed_categories": allowed_categories,
        "allowed_terms": allowed_terms,
        "location_preference": subscriber["location_preference"],
        "excluded_companies_lower": excluded_companies_lower,
    }


def _apply_preference_filters(
    jobs: list[aiosqlite.Row],
    preferences: dict[str, Any],
) -> list[aiosqlite.Row]:
    """Return jobs that satisfy all subscriber preference filters.

    Args:
        jobs: Unfiltered job_postings rows.
        preferences: Parsed preferences from _parse_subscriber_preferences.

    Returns:
        Subset of jobs that pass every filter.
    """
    return [
        job for job in jobs
        if _passes_role_level_filter(job["title"], preferences["role_level"])
        and _passes_category_filter(job["raw_data"], preferences["allowed_categories"])
        and _passes_terms_filter(job["raw_data"], preferences["allowed_terms"])
        and _passes_location_filter(job["location"], preferences["location_preference"])
        and job["company"].lower() not in preferences["excluded_companies_lower"]
    ]


def _passes_role_level_filter(title: str | None, role_level: str) -> bool:
    """Return True if the job title matches the subscriber's role level filter."""
    if role_level == "both" or not title:
        return True

    title_lower = title.lower()

    if role_level == "intern":
        return any(pattern in title_lower for pattern in _INTERN_TITLE_PATTERNS)

    if role_level == "new_grad":
        return any(pattern in title_lower for pattern in _NEW_GRAD_TITLE_PATTERNS)

    return True


def _passes_category_filter(
    raw_data_json: str | None,
    allowed_categories: set[str],
) -> bool:
    """Return True if the job's category is in the subscriber's allowed set."""
    if not allowed_categories:
        # Empty allowed set means subscriber wants all fields.
        return True

    if not raw_data_json:
        return False

    try:
        raw_data: dict[str, Any] = json.loads(raw_data_json)
    except (json.JSONDecodeError, TypeError):
        return False

    category: str = raw_data.get("category", "")
    return category in allowed_categories


def _passes_terms_filter(
    raw_data_json: str | None,
    allowed_terms: set[str],
) -> bool:
    if not allowed_terms:
        return True

    if not raw_data_json:
        return True

    try:
        raw_data: dict[str, Any] = json.loads(raw_data_json)
    except (json.JSONDecodeError, TypeError):
        return True

    job_terms: list[str] = raw_data.get("terms") or []
    if not job_terms:
        return True

    return bool(allowed_terms & set(job_terms))


def _passes_location_filter(location: str | None, location_preference: str) -> bool:
    """Return True if the job's location matches the subscriber's preference."""
    if location_preference == "both":
        return True

    location_lower = (location or "").lower()
    is_remote = "remote" in location_lower

    if location_preference == "remote":
        return is_remote

    # in_person: exclude jobs that are explicitly remote-only.
    return not is_remote


# ---------------------------------------------------------------------------
# Deduplication and grouping
# ---------------------------------------------------------------------------


def _dedup_by_company_title(jobs: list[aiosqlite.Row]) -> list[aiosqlite.Row]:
    """Keep one job per (lower company, lower title) pair, preferring longest description.

    Args:
        jobs: Filtered job_postings rows that may contain duplicates.

    Returns:
        Deduplicated list, one entry per unique (company, title) pair.
    """
    # key → best job seen so far for that (company, title) pair
    best: dict[tuple[str, str], aiosqlite.Row] = {}

    for job in jobs:
        key = (job["company"].lower(), job["title"].lower())
        existing = best.get(key)

        if existing is None:
            best[key] = job
            continue

        # Prefer the entry with the longer description.
        existing_len = len(existing["description"] or "")
        current_len = len(job["description"] or "")
        if current_len > existing_len:
            best[key] = job

    return list(best.values())


def _group_by_category(jobs: list[aiosqlite.Row]) -> dict[str, list[aiosqlite.Row]]:
    """Group jobs by their raw_data category, falling back to 'Other'.

    Args:
        jobs: Deduplicated job_postings rows.

    Returns:
        Dict mapping category name to the list of jobs in that category.
    """
    grouped: dict[str, list[aiosqlite.Row]] = defaultdict(list)

    for job in jobs:
        category = _extract_category(job["raw_data"])
        grouped[category].append(job)

    return dict(grouped)


def _extract_category(raw_data_json: str | None) -> str:
    """Return the category string from a raw_data JSON blob, or 'Other'."""
    if not raw_data_json:
        return "Other"

    try:
        raw_data: dict[str, Any] = json.loads(raw_data_json)
        return raw_data.get("category") or "Other"
    except (json.JSONDecodeError, TypeError):
        return "Other"


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def _render_email(
    jobs_by_category: dict[str, list[aiosqlite.Row]],
    unsubscribe_token: str,
    base_url: str = "",
) -> tuple[str, str]:
    total_jobs = sum(len(jobs) for jobs in jobs_by_category.values())
    subject = f"Joey's CS Job Digest — {total_jobs} new role{'s' if total_jobs != 1 else ''}"

    category_blocks = "".join(
        _render_category_block(category, jobs, unsubscribe_token, base_url)
        for category, jobs in sorted(jobs_by_category.items())
    )

    manage_url = f"{base_url}/manage?token={unsubscribe_token}"

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             color: #1a1a1a; max-width: 640px; margin: 0 auto; padding: 24px 16px;">
  <h1 style="font-size: 22px; margin-bottom: 4px;">{subject}</h1>
  <p style="color: #555; font-size: 14px; margin-top: 0; margin-bottom: 24px;">
    {total_jobs} new posting{'s' if total_jobs != 1 else ''} since your last digest.
  </p>
  {category_blocks}
  <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 32px 0;">
  <p style="font-size: 12px; color: #888; text-align: center;">
    <a href="{manage_url}" style="color: #555;">Manage preferences</a>
  </p>
</body>
</html>"""

    return subject, html_body


def _render_category_block(
    category: str,
    jobs: list[aiosqlite.Row],
    unsubscribe_token: str,
    base_url: str = "",
) -> str:
    job_items = "".join(
        _render_job_item(job, unsubscribe_token, base_url) for job in jobs
    )
    return f"""  <section style="margin-bottom: 32px;">
    <h2 style="font-size: 16px; text-transform: uppercase; letter-spacing: 0.05em;
               color: #333; border-bottom: 2px solid #e0e0e0; padding-bottom: 6px;">
      {category}
    </h2>
    {job_items}
  </section>
"""


def _render_job_item(
    job: aiosqlite.Row, unsubscribe_token: str, base_url: str = ""
) -> str:
    from urllib.parse import quote

    company_encoded = quote(job["company"], safe="")
    hide_url = f"{base_url}/api/digest/hide?token={unsubscribe_token}&company={company_encoded}"
    apply_url = job["source_url"] or "#"

    # Truncate the raw fetched_at timestamp to date-only for readability.
    discovered_display = (job["fetched_at"] or "")[:10]

    return f"""    <div style="margin-bottom: 16px; padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
      <strong>{job['company']}</strong> &mdash; {job['title']}<br>
      <a href="{apply_url}" style="color: #0066cc;">Apply</a>
      &middot; <small>Discovered: {discovered_display}</small>
      &middot; <a href="{hide_url}" style="color: #999; font-size: 12px;">hide</a>
    </div>
"""


# ---------------------------------------------------------------------------
# Resend API delivery
# ---------------------------------------------------------------------------


async def _send_via_resend(
    resend_api_key: str,
    from_address: str,
    to_address: str,
    subject: str,
    html_body: str,
) -> None:
    """POST an email to the Resend API.

    Args:
        resend_api_key: Bearer token.
        from_address: Sender address.
        to_address: Recipient address.
        subject: Email subject line.
        html_body: Fully rendered HTML body.

    Raises:
        httpx.HTTPStatusError: If Resend returns a non-2xx response.
        httpx.HTTPError: For any transport-level failure.
    """
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": from_address,
        "to": [to_address],
        "subject": subject,
        "html": html_body,
    }

    async with httpx.AsyncClient(timeout=_RESEND_TIMEOUT_SECONDS) as client:
        response = await client.post(_RESEND_URL, json=payload, headers=headers)
        response.raise_for_status()

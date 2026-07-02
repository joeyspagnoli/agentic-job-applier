"""Email digest subscription and management endpoints."""

from __future__ import annotations

import html
import json
import os
import uuid

import aiosqlite
import httpx
from fastapi import APIRouter
from loguru import logger
from fastapi import Body
from fastapi import Query
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/digest", tags=["digest"])
pages_router = APIRouter(tags=["digest-pages"])

_DB_PATH = os.environ.get("DB_PATH", "data/jobs.db")
_TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "")
_TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "0x4AAAAAADpiHSEwMjHC13nK")
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_DIGEST_BASE_URL = os.environ.get("DIGEST_BASE_URL", "").rstrip("/")
_RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
_RESEND_URL = "https://api.resend.com/emails"
_FROM_ADDRESS = os.environ.get(
    "DIGEST_FROM_ADDRESS",
    "Joey's CS Job Digest <jobs@cloud.joeyspagnoli-cloud.cc>",
)


def _db_path() -> str:
    return os.environ.get("DB_PATH", _DB_PATH)


class SubscribeRequest(BaseModel):
    name: str
    email: str
    role_level: str
    fields: list[str]
    terms: list[str] = []
    location_preference: str
    excluded_companies: list[str] = []
    turnstile_token: str


class PreferencesUpdateRequest(BaseModel):
    fields: list[str] | None = None
    terms: list[str] | None = None
    role_level: str | None = None
    location_preference: str | None = None
    excluded_companies: list[str] | None = None


async def _send_confirmation_email(
    to_email: str, name: str, confirm_url: str
) -> bool:
    if not _RESEND_API_KEY:
        return False
    html_body = f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            max-width:480px;margin:0 auto;padding:24px 16px;color:#1a1a1a;">
  <h2 style="font-size:20px;margin-bottom:8px;">Confirm your subscription</h2>
  <p style="color:#4a4a4a;font-size:15px;line-height:1.6;">
    Hey {html.escape(name)}, click the button below to start receiving Joey's CS Job Digest
    at 3 pm EST daily.
  </p>
  <a href="{confirm_url}"
     style="display:inline-block;margin:20px 0;padding:12px 28px;
            background:#2c52a0;color:#fff;text-decoration:none;
            border-radius:4px;font-weight:600;font-size:15px;">
    Confirm my subscription
  </a>
  <p style="color:#777;font-size:13px;">
    If you didn't sign up, just ignore this email.
  </p>
</div>"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={
                    "Authorization": f"Bearer {_RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": _FROM_ADDRESS,
                    "to": [to_email],
                    "subject": "Confirm your subscription — Joey's CS Job Digest",
                    "html": html_body,
                },
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPError as exc:
        logger.error("Confirmation email to {} failed: {}", to_email, exc)
        return False


@router.post("/subscribe")
async def subscribe(payload: SubscribeRequest, request: Request) -> JSONResponse:
    """Create a new email digest subscription (unconfirmed)."""

    if _TURNSTILE_SECRET:
        # When a Turnstile secret is configured, a valid token is mandatory.
        # An empty/omitted token must be rejected here — previously the whole
        # verification block was skipped when the token was falsy, which let a
        # caller bypass the CAPTCHA by sending turnstile_token="".
        if not payload.turnstile_token:
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "CAPTCHA verification failed."},
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    _TURNSTILE_VERIFY_URL,
                    data={
                        "secret": _TURNSTILE_SECRET,
                        "response": payload.turnstile_token,
                        "remoteip": request.client.host if request.client else "",
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                # Fail closed if Cloudflare's verify endpoint is unreachable,
                # rather than raising an unhandled 500.
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "message": "CAPTCHA check unavailable. Please try again."},
                )
            if not resp.json().get("success"):
                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "CAPTCHA verification failed."},
                )

    confirm_token = uuid.uuid4().hex
    unsubscribe_token = uuid.uuid4().hex
    fields_json = json.dumps(payload.fields)
    terms_json = json.dumps(payload.terms)
    excluded_json = json.dumps(payload.excluded_companies)

    try:
        async with aiosqlite.connect(_db_path()) as conn:
            await conn.execute(
                """
                INSERT INTO email_subscribers
                    (name, email, role_level, fields, terms, location_preference,
                     excluded_companies, confirm_token, unsubscribe_token, confirmed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    payload.name,
                    payload.email,
                    payload.role_level,
                    fields_json,
                    terms_json,
                    payload.location_preference,
                    excluded_json,
                    confirm_token,
                    unsubscribe_token,
                ),
            )
            await conn.commit()
    except aiosqlite.IntegrityError:
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": "Email already subscribed."},
        )

    confirm_url = f"{_DIGEST_BASE_URL}/api/digest/confirm?token={confirm_token}"
    email_sent = await _send_confirmation_email(payload.email, payload.name, confirm_url)

    if not email_sent:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Could not send confirmation email. Please try again."},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "message": "Check your email for a confirmation link"},
    )


@router.get("/confirm", response_class=HTMLResponse)
async def confirm(token: str = Query(...)) -> HTMLResponse:
    """Confirm a subscription via token from the confirmation email."""

    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, email FROM email_subscribers WHERE confirm_token = ?", (token,)
        )
        row = await cursor.fetchone()
        if row is None:
            return HTMLResponse(
                "<html><body><h2>Error</h2><p>Invalid or expired confirmation link.</p></body></html>",
                status_code=404,
            )
        await conn.execute(
            "UPDATE email_subscribers SET confirmed = 1 WHERE confirm_token = ?",
            (token,),
        )
        await conn.commit()

    from src.digest.pages import confirm_page

    return HTMLResponse(confirm_page(row["email"]))


@router.get("/hide")
async def hide_company(
    token: str = Query(...), company: str = Query(...)
) -> HTMLResponse:
    """Append a company to the subscriber's excluded list, redirect to manage page."""

    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, excluded_companies FROM email_subscribers WHERE unsubscribe_token = ?",
            (token,),
        )
        row = await cursor.fetchone()
        if row is None:
            return HTMLResponse(
                "<html><body><h2>Error</h2><p>Invalid token.</p></body></html>",
                status_code=404,
            )

        excluded: list[str] = json.loads(row["excluded_companies"] or "[]")
        if company not in excluded:
            excluded.append(company)

        await conn.execute(
            "UPDATE email_subscribers SET excluded_companies = ? WHERE id = ?",
            (json.dumps(excluded), row["id"]),
        )
        await conn.commit()

    from src.digest.pages import hide_success_page

    manage_url = f"/manage?token={token}"
    return HTMLResponse(hide_success_page(company, manage_url))


@router.get("/preferences")
async def get_preferences(token: str = Query(...)) -> JSONResponse:
    """Return subscriber preferences by unsubscribe token."""

    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT name, email, role_level, fields, terms, location_preference,
                   excluded_companies, confirmed
            FROM email_subscribers WHERE unsubscribe_token = ?
            """,
            (token,),
        )
        row = await cursor.fetchone()

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Invalid token."},
        )

    return JSONResponse(
        {
            "name": row["name"],
            "email": row["email"],
            "role_level": row["role_level"],
            "fields": json.loads(row["fields"] or "[]"),
            "terms": json.loads(row["terms"] or "[]"),
            "location_preference": row["location_preference"],
            "excluded_companies": json.loads(row["excluded_companies"] or "[]"),
            "confirmed": bool(row["confirmed"]),
        }
    )


@router.put("/preferences")
async def update_preferences(
    token: str = Query(...), payload: PreferencesUpdateRequest = Body(...)
) -> JSONResponse:
    """Update subscriber preferences by unsubscribe token."""

    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id FROM email_subscribers WHERE unsubscribe_token = ?", (token,)
        )
        row = await cursor.fetchone()
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Invalid token."},
            )

        updates: list[str] = []
        params: list[object] = []

        if payload.fields is not None:
            updates.append("fields = ?")
            params.append(json.dumps(payload.fields))
        if payload.terms is not None:
            updates.append("terms = ?")
            params.append(json.dumps(payload.terms))
        if payload.role_level is not None:
            updates.append("role_level = ?")
            params.append(payload.role_level)
        if payload.location_preference is not None:
            updates.append("location_preference = ?")
            params.append(payload.location_preference)
        if payload.excluded_companies is not None:
            updates.append("excluded_companies = ?")
            params.append(json.dumps(payload.excluded_companies))

        if updates:
            params.append(row["id"])
            await conn.execute(
                f"UPDATE email_subscribers SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

    return JSONResponse(content={"status": "ok"})


@router.delete("/unsubscribe")
async def unsubscribe(token: str = Query(...)) -> JSONResponse:
    """Delete a subscription by unsubscribe token."""

    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, email FROM email_subscribers WHERE unsubscribe_token = ?",
            (token,),
        )
        row = await cursor.fetchone()
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Invalid or expired token."},
            )

        await conn.execute(
            "DELETE FROM email_subscribers WHERE id = ?", (row["id"],)
        )
        await conn.commit()

    return JSONResponse(content={"status": "ok"})


@router.post("/send")
async def send_digest() -> dict[str, int]:
    """Admin trigger to run the daily digest sender immediately."""

    from src.digest.sender import send_daily_digest

    result = await send_daily_digest(
        db_path=_db_path(),
        resend_api_key=_RESEND_API_KEY,
        from_address=_FROM_ADDRESS,
        base_url=_DIGEST_BASE_URL,
    )
    return result


# ---------------------------------------------------------------------------
# Public page routes (no /api prefix)
# ---------------------------------------------------------------------------


@pages_router.get("/subscribe", response_class=HTMLResponse)
async def subscribe_page_route() -> HTMLResponse:
    from src.digest.pages import subscribe_page

    return HTMLResponse(subscribe_page(_TURNSTILE_SITE_KEY))


@pages_router.get("/manage", response_class=HTMLResponse)
async def manage_page_route() -> HTMLResponse:
    from src.digest.pages import manage_page

    return HTMLResponse(manage_page())


@pages_router.get("/favicon.ico")
async def favicon_ico() -> FileResponse:
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@pages_router.get("/favicon.png")
async def favicon_png() -> FileResponse:
    return FileResponse("static/favicon.png", media_type="image/png")


@pages_router.get("/apple-touch-icon.png")
async def apple_touch_icon() -> FileResponse:
    return FileResponse("static/apple-touch-icon.png", media_type="image/png")

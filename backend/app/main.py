import json
import os
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parseaddr, parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib import request
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import text

from .services.email_analysis_service import (
    analyze_email_for_user,
    analyze_user_emails_batch,
    get_attention_summary,
    list_user_emails_with_analysis,
    reclassify_existing_emails,
)
from .services.email_normalization_service import normalize_email_message
from .database import engine

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Gmail Attention Dashboard API")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
SECRET_KEY = os.getenv("SECRET_KEY", "")
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured in backend/.env or the process environment")
if SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
if SESSION_COOKIE_SAMESITE == "none" and not SESSION_COOKIE_SECURE:
    raise RuntimeError("SESSION_COOKIE_SECURE must be true when SESSION_COOKIE_SAMESITE is none")
GOOGLE_SCOPE = " ".join(
    [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]
)

print(
    "[OAUTH] config "
    f"client_id_loaded={'yes' if GOOGLE_CLIENT_ID else 'no'} "
    f"client_secret_loaded={'yes' if GOOGLE_CLIENT_SECRET else 'no'} "
    f"redirect_uri={GOOGLE_REDIRECT_URI}"
)

app.state.oauth_states = {}
app.state.fernet = Fernet(urlsafe_b64encode(sha256(SECRET_KEY.encode()).digest()))
SESSION_COOKIE_NAME = "session_user_id"
SESSION_COOKIE_TTL_SECONDS = 60 * 60 * 24 * 7
LOCAL_FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
CORS_ALLOWED_ORIGINS = list(LOCAL_FRONTEND_ORIGINS)
if FRONTEND_URL and FRONTEND_URL not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return app.state.fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    return app.state.fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def _fetch_json(url: str, data: dict | None = None, headers: dict | None = None, method: str = "GET"):
    payload = None
    request_headers = dict(headers or {})
    if data is not None:
        payload = urlencode(data).encode("utf-8")
        if "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

    http_request = request.Request(url, data=payload, headers=request_headers, method=method)
    with request.urlopen(http_request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _upsert_user(google_user: dict) -> str:
    google_user_id = google_user.get("id") or google_user.get("sub")
    email = google_user.get("email")
    name = google_user.get("name") or google_user.get("given_name") or email
    picture_url = google_user.get("picture")

    with engine.begin() as connection:
        existing = connection.execute(
            text(
                """
                SELECT id
                FROM users
                WHERE google_user_id = :google_user_id
                   OR email = :email
                LIMIT 1
                """
            ),
            {
                "google_user_id": google_user_id,
                "email": email,
            },
        ).fetchone()

        if existing:
            user_id = existing[0]
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET google_user_id = :google_user_id,
                        email = :email,
                        name = :name,
                        picture_url = :picture_url,
                        updated_at = NOW()
                    WHERE id = :user_id
                    """
                ),
                {
                    "google_user_id": google_user_id,
                    "email": email,
                    "name": name,
                    "picture_url": picture_url,
                    "user_id": user_id,
                },
            )
            return str(user_id)

        new_user = connection.execute(
            text(
                """
                INSERT INTO users (google_user_id, email, name, picture_url)
                VALUES (:google_user_id, :email, :name, :picture_url)
                RETURNING id
                """
            ),
            {
                "google_user_id": google_user_id,
                "email": email,
                "name": name,
                "picture_url": picture_url,
            },
        ).fetchone()
        return str(new_user[0])


def _store_tokens(user_id: str, access_token: str, refresh_token: str | None, expires_in: int | None):
    expiry = None
    if expires_in is not None:
        expiry = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(expires_in)))

    encrypted_access = encrypt_secret(access_token)
    encrypted_refresh = encrypt_secret(refresh_token) if refresh_token else None

    with engine.begin() as connection:
        existing = connection.execute(
            text(
                """
                SELECT id
                FROM oauth_tokens
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).fetchone()

        if existing:
            connection.execute(
                text(
                    """
                    UPDATE oauth_tokens
                    SET access_token_encrypted = :access_token_encrypted,
                        refresh_token_encrypted = :refresh_token_encrypted,
                        token_expiry = :token_expiry,
                        scope = :scope,
                        updated_at = NOW()
                    WHERE user_id = :user_id
                    """
                ),
                {
                    "user_id": user_id,
                    "access_token_encrypted": encrypted_access,
                    "refresh_token_encrypted": encrypted_refresh,
                    "token_expiry": expiry,
                    "scope": GOOGLE_SCOPE,
                },
            )
            return

        connection.execute(
            text(
                """
                INSERT INTO oauth_tokens (
                    user_id,
                    access_token_encrypted,
                    refresh_token_encrypted,
                    token_expiry,
                    scope
                )
                VALUES (
                    :user_id,
                    :access_token_encrypted,
                    :refresh_token_encrypted,
                    :token_expiry,
                    :scope
                )
                """
            ),
            {
                "user_id": user_id,
                "access_token_encrypted": encrypted_access,
                "refresh_token_encrypted": encrypted_refresh,
                "token_expiry": expiry,
                "scope": GOOGLE_SCOPE,
            },
        )


def _build_session_cookie_value(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "expires_at": int(time.time()) + SESSION_COOKIE_TTL_SECONDS,
    }
    return app.state.fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")


def _decode_session_cookie_value(raw_value: str | None) -> str | None:
    if not raw_value:
        return None

    try:
        payload = json.loads(app.state.fernet.decrypt(raw_value.encode("utf-8")).decode("utf-8"))
        if payload.get("expires_at", 0) < int(time.time()):
            return None
        return payload.get("user_id")
    except Exception:
        return raw_value if raw_value else None


def _get_session_user(request: Request):
    raw_user_id = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = _decode_session_cookie_value(raw_user_id)
    if not user_id:
        return None

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, google_user_id, email, name, picture_url
                FROM users
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).fetchone()

    if not row:
        return None

    return {
        "id": str(row[0]),
        "google_user_id": row[1],
        "email": row[2],
        "name": row[3],
        "picture_url": row[4],
    }


def _require_authenticated_user(request: Request):
    user = _get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _normalize_token_expiry(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        expiry = value
    elif isinstance(value, str):
        expiry_text = value.strip()
        if not expiry_text:
            return None
        if expiry_text.endswith("Z"):
            expiry_text = expiry_text[:-1] + "+00:00"
        try:
            expiry = datetime.fromisoformat(expiry_text)
        except ValueError:
            return None
    else:
        return None

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return expiry.astimezone(timezone.utc)


def _get_user_oauth_record(user_id: str):
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT access_token_encrypted, refresh_token_encrypted, token_expiry
                FROM oauth_tokens
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).fetchone()

    if not row:
        return None, None, None

    access_token_encrypted, refresh_token_encrypted, token_expiry = row
    access_token = decrypt_secret(access_token_encrypted) if access_token_encrypted else ""
    refresh_token = decrypt_secret(refresh_token_encrypted) if refresh_token_encrypted else None

    expiry = _normalize_token_expiry(token_expiry)
    return access_token, refresh_token, expiry


def _get_user_oauth_scope(user_id: str) -> str:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT scope
                FROM oauth_tokens
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).fetchone()

    return str(row[0] or "") if row else ""


def _ensure_fresh_google_access_token(user_id: str, access_token: str, refresh_token: str | None):
    if not access_token and not refresh_token:
        raise HTTPException(status_code=401, detail="No Google OAuth token available")

    token_expiry = None
    with engine.connect() as connection:
        token_row = connection.execute(
            text(
                """
                SELECT token_expiry
                FROM oauth_tokens
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).fetchone()

    if token_row and token_row[0]:
        token_expiry = _normalize_token_expiry(token_row[0])

    if refresh_token and (not access_token or not token_expiry or token_expiry <= datetime.now(timezone.utc) - timedelta(minutes=1)):
        refresh_payload = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        refreshed = _fetch_json(
            "https://oauth2.googleapis.com/token",
            data=refresh_payload,
            method="POST",
        )
        access_token = refreshed.get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="Unable to refresh Google access token")
        expires_in = refreshed.get("expires_in")
        _store_tokens(user_id, access_token, refresh_token, expires_in)

    if not access_token:
        raise HTTPException(status_code=401, detail="Missing Google access token")

    return access_token


def _parse_sender(from_header: str | None):
    if not from_header:
        return None, None

    sender_name, sender_email = parseaddr(from_header)
    sender_name = sender_name.strip() if sender_name else None
    sender_email = sender_email.strip() if sender_email else None
    return sender_name, sender_email


def _parse_received_at(message: dict):
    internal_date = message.get("internalDate")
    if internal_date:
        try:
            return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            pass

    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == "date":
            date_value = header.get("value")
            if date_value:
                try:
                    parsed = parsedate_to_datetime(date_value)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except (TypeError, ValueError):
                    pass

    return datetime.now(timezone.utc)


def _build_gmail_message_url(message_id: str) -> str:
    if not message_id:
        return ""
    return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"


def _fetch_gmail_metadata(access_token: str, refresh_token: str | None, message_id: str):
    """Fetch one list-row payload in an isolated Gmail client for thread safety."""
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    gmail_service = build("gmail", "v1", credentials=credentials)
    return gmail_service.users().messages().get(
        userId="me",
        id=message_id,
        format="metadata",
        metadataHeaders=["From", "Subject", "Date"],
    ).execute()


def _fetch_gmail_body(access_token: str, refresh_token: str | None, message_id: str) -> dict[str, str]:
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    gmail_service = build("gmail", "v1", credentials=credentials)
    message = gmail_service.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()
    normalized = normalize_email_message(message)
    html_body = normalized.get("html_body", "")
    inline_images: dict[str, str] = {}

    def collect_inline_images(part: dict) -> None:
        headers = {str(header.get("name", "")).lower(): str(header.get("value", "")) for header in part.get("headers", [])}
        content_id = headers.get("content-id", "").strip().strip("<>")
        mime_type = str(part.get("mimeType", "")).lower()
        body = part.get("body") or {}
        data = body.get("data")
        if content_id and mime_type.startswith("image/"):
            if not data and body.get("attachmentId"):
                data = gmail_service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=body["attachmentId"]
                ).execute().get("data")
            if data:
                padded_data = data + "=" * (-len(data) % 4)
                image_data = urlsafe_b64encode(urlsafe_b64decode(padded_data)).decode("ascii")
                inline_images[content_id] = f"data:{mime_type};base64,{image_data}"
        for child in part.get("parts") or []:
            collect_inline_images(child)

    collect_inline_images(message.get("payload") or {})
    for content_id, data_url in inline_images.items():
        html_body = re.sub(rf"cid:\s*<?{re.escape(content_id)}>?", data_url, html_body, flags=re.IGNORECASE)

    return {
        "body": normalized.get("body_text", ""),
        "original_body": normalized.get("original_body", ""),
        "html_body": html_body,
    }


def _attach_gmail_bodies(user_id: str, emails: list[dict]) -> list[dict]:
    if not emails:
        return emails

    try:
        access_token, refresh_token, _ = _get_user_oauth_record(user_id)
        access_token = _ensure_fresh_google_access_token(user_id, access_token, refresh_token)
    except Exception as exc:
        print(f"[API] unable to load message bodies user_id={user_id} error={exc}")
        return emails

    worker_count = min(max(int(os.getenv("GMAIL_DETAIL_WORKERS", "6")), 1), 8, len(emails))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_fetch_gmail_body, access_token, refresh_token, email["gmail_message_id"]): email
            for email in emails
            if email.get("gmail_message_id")
        }
        for future in as_completed(futures):
            email = futures[future]
            try:
                email.update(future.result())
            except Exception as exc:
                print(f"[API] body fetch failure message_id={email['gmail_message_id']} error={exc}")
                email["body"] = ""
                email["original_body"] = ""
                email["html_body"] = ""

    return emails


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/config")
def get_client_config():
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "google_redirect_uri": GOOGLE_REDIRECT_URI,
    }


@app.get("/api/auth/google")
def google_oauth_start():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI or not FRONTEND_URL:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    state = secrets.token_urlsafe(32)
    app.state.oauth_states[state] = time.time() + 600
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    redirect_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(redirect_url, status_code=307)


@app.get("/api/auth/google/callback")
def google_oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?auth=error&reason={error}", status_code=302)

    if not code or not state or state not in app.state.oauth_states:
        return RedirectResponse(f"{FRONTEND_URL}/?auth=error&reason=invalid_state", status_code=302)

    del app.state.oauth_states[state]

    token_payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        token_response = _fetch_json(
            "https://oauth2.googleapis.com/token",
            data=token_payload,
            method="POST",
        )
    except HTTPError as exc:
        try:
            google_error = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            google_error = {}
        if not isinstance(google_error, dict):
            google_error = {}

        safe_error = {}
        for key in ("error", "error_description", "error_uri"):
            value = google_error.get(key)
            if value is None:
                continue
            safe_value = str(value)
            for sensitive_value in (GOOGLE_CLIENT_SECRET, code):
                if sensitive_value:
                    safe_value = safe_value.replace(sensitive_value, "[REDACTED]")
            safe_error[key] = safe_value.replace("\r", " ").replace("\n", " ")
        safe_error.setdefault("error", "unknown")
        print(f"[OAUTH] Google token exchange failed status={exc.code} response={json.dumps(safe_error)}")
        return RedirectResponse(f"{FRONTEND_URL}/?auth=error&reason=token_exchange_failed", status_code=302)

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")

    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}/?auth=error&reason=missing_access_token", status_code=302)

    user_info = _fetch_json(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    user_id = _upsert_user(user_info)
    _store_tokens(user_id, access_token, refresh_token, expires_in)

    response = RedirectResponse(f"{FRONTEND_URL}/?auth=success", status_code=302)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _build_session_cookie_value(str(user_id)),
        max_age=SESSION_COOKIE_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
    )
    return response


@app.post("/api/auth/disconnect")
def disconnect_user():
    cleared = JSONResponse({"success": True}, status_code=200)
    cleared.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return cleared


@app.get("/api/auth/me")
def get_current_user(request: Request):
    user = _require_authenticated_user(request)
    return user


@app.post("/api/emails/analyze")
def analyze_single_email(request: Request, payload: dict | None = Body(default=None)):
    user = _require_authenticated_user(request)
    if payload is None:
        payload = {}

    gmail_message_id = (payload.get("gmail_message_id") or payload.get("id") or payload.get("gmailId"))
    if not gmail_message_id:
        raise HTTPException(status_code=400, detail="gmail_message_id is required")

    return analyze_email_for_user(user["id"], gmail_message_id)


@app.post("/api/emails/{email_id}/analyze")
def analyze_email_by_database_id(request: Request, email_id: str):
    user = _require_authenticated_user(request)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT gmail_message_id
                FROM emails
                WHERE id = :email_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"email_id": email_id, "user_id": user["id"]},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    return analyze_email_for_user(user["id"], row[0])


@app.post("/api/emails/analyze-batch")
def analyze_email_batch(request: Request, payload: dict | None = Body(default=None)):
    user = _require_authenticated_user(request)
    if payload is None:
        payload = {}

    gmail_message_ids = payload.get("gmail_message_ids") or []
    results = analyze_user_emails_batch(
        user["id"],
        gmail_message_ids if gmail_message_ids else None,
        force_reclassify=bool(payload.get("force_reclassify")),
    )
    return {"success": True, "analyzed": len(results), "results": results}


@app.post("/api/emails/reclassify-existing")
def reclassify_existing_email_analyses(request: Request):
    user = _require_authenticated_user(request)
    return {"success": True, **reclassify_existing_emails(user["id"])}


MAX_REPLY_ATTACHMENTS = 10
MAX_REPLY_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_REPLY_TOTAL_BYTES = 25 * 1024 * 1024
BLOCKED_REPLY_CONTENT_TYPES = {
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/x-sh",
    "application/x-httpd-php",
    "application/javascript",
    "text/javascript",
}
BLOCKED_REPLY_EXTENSIONS = {".exe", ".bat", ".cmd", ".com", ".js", ".ps1", ".sh", ".vbs", ".php"}


def _reply_plain_text(body: str) -> str:
    plain_text = re.sub(r"<br\s*/?>", "\n", body or "", flags=re.I)
    plain_text = re.sub(r"</(p|div|li|ul|ol)>", "\n", plain_text, flags=re.I)
    plain_text = re.sub(r"<[^>]+>", "", plain_text)
    return re.sub(r"\n{3,}", "\n\n", plain_text).strip()


def _validated_addresses(value: str, field_name: str, required: bool = False) -> list[str]:
    value = (value or "").strip()
    if not value:
        if required:
            raise HTTPException(status_code=400, detail=f"{field_name} must include a valid email address")
        return []
    if "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail=f"{field_name} contains an invalid email address")

    addresses = getaddresses([value])
    if not addresses or any(not email or "@" not in email or email.startswith("@") or email.endswith("@") for _, email in addresses):
        raise HTTPException(status_code=400, detail=f"{field_name} must include valid email addresses")
    return [formataddr((name, email)) if name else email for name, email in addresses]


@app.post("/api/emails/{email_id}/reply")
async def reply_to_email(
    request: Request,
    email_id: str,
    body: str = Form(default=""),
    to: str = Form(default=""),
    cc: str = Form(default=""),
    bcc: str = Form(default=""),
    subject: str = Form(default=""),
    attachments: list[UploadFile] = File(default=[]),
):
    user = _require_authenticated_user(request)
    body = str(body or "").strip()
    plain_body = _reply_plain_text(body)
    if not plain_body:
        raise HTTPException(status_code=400, detail="Reply body cannot be empty")
    if len(attachments) > MAX_REPLY_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"You can attach up to {MAX_REPLY_ATTACHMENTS} files")

    uploaded_files = []
    total_bytes = 0
    for attachment in attachments:
        filename = (attachment.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Every attachment must have a filename")

        file_bytes = await attachment.read()
        if len(file_bytes) > MAX_REPLY_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail=f"{filename} exceeds the 10 MB attachment limit")
        if attachment.content_type in BLOCKED_REPLY_CONTENT_TYPES or Path(filename).suffix.lower() in BLOCKED_REPLY_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"The file type for {filename} is not allowed")

        total_bytes += len(file_bytes)
        if total_bytes > MAX_REPLY_TOTAL_BYTES:
            raise HTTPException(status_code=400, detail="The combined attachment size cannot exceed 25 MB")

        uploaded_files.append(
            {
                "filename": filename,
                "content": file_bytes,
                "content_type": attachment.content_type or "application/octet-stream",
            }
        )

    with engine.connect() as connection:
        email_row = connection.execute(
            text(
                """
                SELECT id, gmail_message_id, gmail_thread_id, sender, subject
                FROM emails
                WHERE id = :email_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"email_id": email_id, "user_id": user["id"]},
        ).fetchone()

    if not email_row:
        raise HTTPException(status_code=404, detail="Email not found")

    _, gmail_message_id, gmail_thread_id, stored_recipient, original_subject = email_row
    if not gmail_message_id or not gmail_thread_id:
        raise HTTPException(status_code=422, detail="This email is missing Gmail thread information")

    required_scope = "https://www.googleapis.com/auth/gmail.send"
    if required_scope not in _get_user_oauth_scope(user["id"]).split():
        raise HTTPException(
            status_code=403,
            detail="Gmail send permission is required. Please sign in with Google again to reauthorize sending.",
        )

    access_token, refresh_token, _ = _get_user_oauth_record(user["id"])
    access_token = _ensure_fresh_google_access_token(user["id"], access_token, refresh_token)
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    gmail_service = build("gmail", "v1", credentials=credentials)

    try:
        original = gmail_service.users().messages().get(
            userId="me",
            id=gmail_message_id,
            format="metadata",
            metadataHeaders=["Message-ID", "References", "Reply-To", "From"],
        ).execute()
        original_headers = {
            (header.get("name") or "").lower(): header.get("value", "")
            for header in original.get("payload", {}).get("headers", [])
        }

        default_recipient = original_headers.get("reply-to") or original_headers.get("from") or stored_recipient
        recipients = _validated_addresses(to or default_recipient, "To", required=True)
        cc_recipients = _validated_addresses(cc, "Cc")
        bcc_recipients = _validated_addresses(bcc, "Bcc")
        entered_subject = (subject or "").strip() or (original_subject or "").strip()
        if not entered_subject.lower().startswith("re:"):
            entered_subject = f"Re: {entered_subject}" if entered_subject else "Re: (no subject)"

        message = EmailMessage()
        message["To"] = ", ".join(recipients)
        if cc_recipients:
            message["Cc"] = ", ".join(cc_recipients)
        if bcc_recipients:
            message["Bcc"] = ", ".join(bcc_recipients)
        message["Subject"] = entered_subject
        if original_headers.get("message-id"):
            message["In-Reply-To"] = original_headers["message-id"]
            references = original_headers.get("references", "").strip()
            message["References"] = f"{references} {original_headers['message-id']}".strip()
        message.set_content(plain_body)
        if body != plain_body:
            message.add_alternative(body, subtype="html")
        for attachment in uploaded_files:
            maintype, subtype = attachment["content_type"].split("/", 1) if "/" in attachment["content_type"] else ("application", "octet-stream")
            message.add_attachment(
                attachment["content"],
                maintype=maintype,
                subtype=subtype,
                filename=attachment["filename"],
            )
        raw_message = urlsafe_b64encode(message.as_bytes()).decode("ascii")

        sent = gmail_service.users().messages().send(
            userId="me",
            body={"raw": raw_message, "threadId": gmail_thread_id},
        ).execute()
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[REPLY] failed email_id={email_id} message_id={gmail_message_id} error={exc}")
        google_status = getattr(getattr(exc, "resp", None), "status", None)
        if google_status == 401:
            raise HTTPException(status_code=401, detail="Google authorization expired. Sign in with Google again to send this reply.") from exc
        if google_status == 403:
            raise HTTPException(status_code=403, detail="Gmail denied this send. Reauthorize Gmail sending permission and try again.") from exc
        if google_status == 429:
            raise HTTPException(status_code=503, detail="Gmail is temporarily rate-limiting sends. Please try again shortly.") from exc
        raise HTTPException(status_code=502, detail="Gmail could not send the reply. Check the recipient and try again.") from exc

    return {
        "success": True,
        "message": "Reply sent",
        "gmail_message_id": sent.get("id"),
        "gmail_thread_id": sent.get("threadId") or gmail_thread_id,
        "attachments": len(uploaded_files),
    }


@app.get("/api/emails/summary")
def get_emails_summary(request: Request):
    user = _require_authenticated_user(request)
    return get_attention_summary(user["id"])


@app.post("/api/gmail/sync")
def sync_gmail(request: Request):
    user = _require_authenticated_user(request)
    user_id = user["id"]

    access_token, refresh_token, _ = _get_user_oauth_record(user_id)
    access_token = _ensure_fresh_google_access_token(user_id, access_token, refresh_token)

    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    gmail_service = build("gmail", "v1", credentials=credentials)

    sync_started_at = time.perf_counter()
    listing_started_at = time.perf_counter()
    message_listing = gmail_service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=30,
    ).execute()
    print(f"[SYNC_TIMING] message_list_seconds={time.perf_counter() - listing_started_at:.3f}")

    message_ids = [message["id"] for message in message_listing.get("messages", [])]
    created = 0
    updated = 0
    existing = 0
    analyzed = 0
    analysis_failures = 0
    analysis_queue: list[str] = []

    print(f"[SYNC] fetched={len(message_ids)}")

    detail_started_at = time.perf_counter()
    detail_results: dict[str, dict] = {}
    detail_failures = 0
    detail_workers = min(max(int(os.getenv("GMAIL_DETAIL_WORKERS", "6")), 1), 8)
    with ThreadPoolExecutor(max_workers=detail_workers) as executor:
        futures = {
            executor.submit(_fetch_gmail_metadata, access_token, refresh_token, message_id): message_id
            for message_id in message_ids
        }
        for future in as_completed(futures):
            message_id = futures[future]
            try:
                detail_results[message_id] = future.result()
            except Exception as exc:
                detail_failures += 1
                print(f"[SYNC] metadata failure message_id={message_id} error={exc}")
    print(
        f"[SYNC_TIMING] metadata_seconds={time.perf_counter() - detail_started_at:.3f} "
        f"workers={detail_workers} failures={detail_failures}"
    )

    database_started_at = time.perf_counter()
    parse_seconds = 0.0
    for message_id in message_ids:
        detail = detail_results.get(message_id)
        if not detail:
            continue

        parse_started_at = time.perf_counter()
        headers = detail.get("payload", {}).get("headers", [])
        header_lookup = {
            (header.get("name") or "").lower(): header.get("value", "")
            for header in headers
        }

        sender_name, sender_email = _parse_sender(header_lookup.get("from"))
        subject = header_lookup.get("subject", "")
        gmail_thread_id = detail.get("threadId")
        received_at = _parse_received_at(detail)
        gmail_url = _build_gmail_message_url(message_id)
        snippet = detail.get("snippet", "")
        parse_seconds += time.perf_counter() - parse_started_at

        with engine.begin() as connection:
            existing_row = connection.execute(
                text(
                    """
                    SELECT e.id, e.sender, e.sender_name, e.subject, e.snippet,
                           e.gmail_thread_id, e.received_at, a.id AS analysis_id
                    FROM emails e
                    LEFT JOIN email_analysis a ON a.email_id = e.id
                    WHERE e.user_id = :user_id
                      AND e.gmail_message_id = :gmail_message_id
                    LIMIT 1
                    """
                ),
                {
                    "user_id": user_id,
                    "gmail_message_id": message_id,
                },
            ).fetchone()

            metadata_changed = bool(
                existing_row
                and (
                    existing_row[1] != sender_email
                    or existing_row[2] != sender_name
                    or existing_row[3] != subject
                    or existing_row[4] != snippet
                    or existing_row[5] != gmail_thread_id
                )
            )
            if existing_row:
                connection.execute(
                    text(
                        """
                        UPDATE emails
                        SET gmail_thread_id = :gmail_thread_id,
                            sender = :sender,
                            sender_name = :sender_name,
                            subject = :subject,
                            received_at = :received_at,
                            gmail_url = :gmail_url,
                            snippet = :snippet,
                            updated_at = NOW()
                        WHERE user_id = :user_id
                          AND gmail_message_id = :gmail_message_id
                        """
                    ),
                    {
                        "user_id": user_id,
                        "gmail_message_id": message_id,
                        "gmail_thread_id": gmail_thread_id,
                        "sender": sender_email,
                        "sender_name": sender_name,
                        "subject": subject,
                        "received_at": received_at,
                        "gmail_url": gmail_url,
                        "snippet": snippet,
                    },
                )
                updated += 1
                existing += 1
            else:
                connection.execute(
                    text(
                        """
                        INSERT INTO emails (
                            user_id,
                            gmail_message_id,
                            gmail_thread_id,
                            sender,
                            sender_name,
                            subject,
                            received_at,
                            gmail_url,
                            snippet
                        )
                        VALUES (
                            :user_id,
                            :gmail_message_id,
                            :gmail_thread_id,
                            :sender,
                            :sender_name,
                            :subject,
                            :received_at,
                            :gmail_url,
                            :snippet
                        )
                        """
                    ),
                    {
                        "user_id": user_id,
                        "gmail_message_id": message_id,
                        "gmail_thread_id": gmail_thread_id,
                        "sender": sender_email,
                        "sender_name": sender_name,
                        "subject": subject,
                        "received_at": received_at,
                        "gmail_url": gmail_url,
                        "snippet": snippet,
                    },
                )
                created += 1

        if not existing_row or existing_row[7] is None or metadata_changed:
            analysis_queue.append(message_id)

    print(
        f"[SYNC_TIMING] parse_seconds={parse_seconds:.3f} "
        f"database_seconds={time.perf_counter() - database_started_at:.3f}"
    )

    analysis_started_at = time.perf_counter()
    analysis_workers = min(max(int(os.getenv("GMAIL_ANALYSIS_WORKERS", "4")), 1), 6)
    with ThreadPoolExecutor(max_workers=analysis_workers) as executor:
        futures = {
            executor.submit(analyze_email_for_user, user_id, message_id): message_id
            for message_id in analysis_queue
        }
        for future in as_completed(futures):
            message_id = futures[future]
            try:
                future.result()
                analyzed += 1
            except Exception as exc:
                analysis_failures += 1
                print(f"[SYNC] analysis failure message_id={message_id} error={exc}")
    print(
        f"[SYNC_TIMING] analysis_seconds={time.perf_counter() - analysis_started_at:.3f} "
        f"queued={len(analysis_queue)} workers={analysis_workers}"
    )

    print(
        f"[SYNC_TIMING] total_seconds={time.perf_counter() - sync_started_at:.3f} "
        f"fetched={len(message_ids)} inserted={created} existing={existing} updated={updated} "
        f"analyzed={analyzed} analysis_failures={analysis_failures}"
    )

    return {
        "success": True,
        "fetched": len(message_ids),
        "created": created,
        "updated": updated,
        "existing": existing,
        "analyzed": analyzed,
        "analysis_failures": analysis_failures,
    }


@app.get("/api/emails")
def list_imported_emails(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    category: str | None = Query(default=None),
    include_analysis: bool = Query(default=True),
):
    user = _require_authenticated_user(request)
    user_id = user["id"]

    allowed_categories = {
        "Action Required",
        "Upcoming Deadlines",
        "Events & Invitations",
        "Awaiting Response",
        "Opportunities",
        "Important Alerts",
        "Updates",
        "Other",
    }
    if category is not None and category not in allowed_categories:
        raise HTTPException(status_code=400, detail="Invalid category")

    if include_analysis:
        payload = _attach_gmail_bodies(
            user_id,
            list_user_emails_with_analysis(user_id, category=category, limit=limit),
        )
        print(f"[API] returned={len(payload)} include_analysis={include_analysis} first_category={payload[0].get('analysis', {}).get('category') if payload else None}")
        return payload

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    e.id,
                    e.gmail_message_id,
                    e.gmail_thread_id,
                    e.sender,
                    e.sender_name,
                    e.subject,
                    e.received_at,
                    e.gmail_url,
                    e.snippet,
                    e.created_at,
                    e.updated_at
                FROM emails e
                WHERE e.user_id = :user_id
                  AND (:category IS NULL OR EXISTS (
                    SELECT 1 FROM email_analysis a
                    WHERE a.email_id = e.id
                      AND COALESCE(a.primary_category, a.category) = :category
                  ))
                ORDER BY e.received_at DESC NULLS LAST, e.created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "category": category, "limit": limit},
        ).fetchall()

    payload = [
        {
            "id": str(row[0]),
            "gmail_message_id": row[1],
            "gmail_thread_id": row[2],
            "sender": row[3],
            "sender_name": row[4],
            "subject": row[5],
            "received_at": row[6].isoformat() if row[6] else None,
            "gmail_url": row[7],
            "snippet": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "updated_at": row[10].isoformat() if row[10] else None,
        }
        for row in rows
    ]
    payload = _attach_gmail_bodies(user_id, payload)
    print(f"[API] returned={len(payload)} include_analysis={include_analysis} has_analysis_fields={False}")
    return payload


@app.get("/")
def read_root():
    return {"message": "Gmail Attention Dashboard API"}

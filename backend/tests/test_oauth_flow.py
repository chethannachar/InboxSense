import base64
import io
import json
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_main
from app.main import _attach_gmail_bodies, _fetch_json, _normalize_token_expiry, app
from app.services.email_analysis_service import (
    _build_deterministic_classification,
    extract_local_signals,
    normalize_email_message,
    should_use_gemini,
    _apply_attention_policy,
    validate_classification,
)

client = TestClient(app)


def test_google_auth_redirect_has_gmail_scope_and_state():
    response = client.get("/api/auth/google", follow_redirects=False)

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert "https://www.googleapis.com/auth/gmail.readonly" in query["scope"][0].split()
    assert "https://www.googleapis.com/auth/gmail.send" in query["scope"][0].split()
    assert "https://www.googleapis.com/auth/userinfo.email" in query["scope"][0].split()
    assert "https://www.googleapis.com/auth/userinfo.profile" in query["scope"][0].split()
    assert "state" in query
    assert query["state"][0]


def test_cors_allows_local_and_configured_frontend_origins():
    assert "http://localhost:5173" in app_main.CORS_ALLOWED_ORIGINS
    assert "http://127.0.0.1:5173" in app_main.CORS_ALLOWED_ORIGINS
    assert app_main.FRONTEND_URL in app_main.CORS_ALLOWED_ORIGINS
    assert "*" not in app_main.CORS_ALLOWED_ORIGINS


def test_oauth_callback_sets_cross_site_cookie_attributes(monkeypatch):
    state = "cross-site-oauth-test-state"
    app.state.oauth_states[state] = 0
    monkeypatch.setattr(app_main, "FRONTEND_URL", "https://inbox-sense.vercel.app")
    monkeypatch.setattr(app_main, "SESSION_COOKIE_SAMESITE", "none")
    monkeypatch.setattr(app_main, "SESSION_COOKIE_SECURE", True)
    token_responses = iter([
        {"access_token": "test-access-token", "refresh_token": "test-refresh-token", "expires_in": 3600},
        {"id": "google-user", "email": "user@example.com", "name": "Inbox Sense User"},
    ])
    monkeypatch.setattr(app_main, "_fetch_json", lambda *args, **kwargs: next(token_responses))
    monkeypatch.setattr(app_main, "_upsert_user", lambda user: "test-user-id")
    monkeypatch.setattr(app_main, "_store_tokens", lambda *args: None)

    response = client.get(
        "/api/auth/google/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://inbox-sense.vercel.app/?auth=success"
    cookie = response.headers["set-cookie"].lower()
    assert "samesite=none" in cookie
    assert "secure" in cookie
    assert "httponly" in cookie


def test_google_oauth_token_failure_logs_safe_google_error(monkeypatch, capsys):
    state = "oauth-error-test-state"
    secret = "oauth-error-test-secret"
    code = "oauth-error-test-code"
    exchange = {"calls": 0}
    app.state.oauth_states[state] = 0

    def fail_token_exchange(*args, **kwargs):
        exchange["calls"] += 1
        exchange["url"] = args[0]
        exchange["method"] = kwargs["method"]
        exchange["payload"] = kwargs["data"]
        body = json.dumps({
            "error": "invalid_client",
            "error_description": f"Rejected secret {secret} and code {code}",
        }).encode()
        raise HTTPError(args[0], 401, "Unauthorized", {}, io.BytesIO(body))

    monkeypatch.setattr("app.main.GOOGLE_CLIENT_SECRET", secret)
    monkeypatch.setattr("app.main._fetch_json", fail_token_exchange)
    response = client.get(
        "/api/auth/google/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )

    logged_error = capsys.readouterr().out
    assert response.status_code == 302
    assert "invalid_client" in logged_error
    assert secret not in logged_error
    assert code not in logged_error
    assert exchange["calls"] == 1
    assert exchange["url"] == "https://oauth2.googleapis.com/token"
    assert exchange["method"] == "POST"
    assert set(exchange["payload"]) == {"code", "client_id", "client_secret", "redirect_uri", "grant_type"}
    assert exchange["payload"]["code"] == code
    assert exchange["payload"]["client_id"] == app_main.GOOGLE_CLIENT_ID
    assert exchange["payload"]["client_secret"] == secret
    assert exchange["payload"]["redirect_uri"] == app_main.GOOGLE_REDIRECT_URI
    assert exchange["payload"]["grant_type"] == "authorization_code"


def test_fetch_json_posts_form_encoded_data(monkeypatch):
    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(http_request, timeout):
        captured["request"] = http_request
        return DummyResponse()

    monkeypatch.setattr("app.main.request.urlopen", fake_urlopen)
    result = _fetch_json(
        "https://oauth2.googleapis.com/token",
        data={"code": "test-code+value", "client_secret": "test-secret", "grant_type": "authorization_code"},
        method="POST",
    )

    parsed_body = parse_qs(captured["request"].data.decode("utf-8"))
    assert result == {}
    assert captured["request"].method == "POST"
    assert captured["request"].get_header("Content-type") == "application/x-www-form-urlencoded"
    assert parsed_body["code"] == ["test-code+value"]
    assert parsed_body["grant_type"] == ["authorization_code"]


def test_me_requires_authentication():
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_gmail_sync_requires_authentication():
    response = client.post("/api/gmail/sync")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_reply_requires_authentication():
    response = client.post("/api/emails/email-1/reply", data={"body": "Thanks"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_reply_rejects_empty_body(monkeypatch):
    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})

    response = client.post("/api/emails/email-1/reply", data={"body": "  "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Reply body cannot be empty"


def test_reply_requires_gmail_send_scope(monkeypatch):
    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})

    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            class DummyResult:
                def fetchone(self):
                    return ("email-1", "gmail-message", "gmail-thread", "sender@example.com", "Original subject")

            return DummyResult()

    monkeypatch.setattr(
        "app.main.engine",
        type("EngineStub", (), {"connect": staticmethod(lambda: DummyConnection())}),
    )
    monkeypatch.setattr("app.main._get_user_oauth_scope", lambda user_id: "https://www.googleapis.com/auth/gmail.readonly")

    response = client.post("/api/emails/email-1/reply", data={"body": "Thanks"})

    assert response.status_code == 403
    assert "reauthorize" in response.json()["detail"]


def test_reply_sends_same_gmail_thread(monkeypatch):
    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})

    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            class DummyResult:
                def fetchone(self):
                    return ("email-1", "gmail-message", "gmail-thread", "sender@example.com", "Project update")

            return DummyResult()

    sent = {}

    class DummyMessages:
        def get(self, **kwargs):
            return type("GetRequest", (), {"execute": lambda self: {"payload": {"headers": [{"name": "Message-ID", "value": "<original@example.com>"}]}}})()

        def send(self, **kwargs):
            sent.update(kwargs)
            return type("SendRequest", (), {"execute": lambda self: {"id": "sent-message", "threadId": "gmail-thread"}})()

    class DummyGmailService:
        def users(self):
            return self

        def messages(self):
            return DummyMessages()

    monkeypatch.setattr(
        "app.main.engine",
        type("EngineStub", (), {"connect": staticmethod(lambda: DummyConnection())}),
    )
    monkeypatch.setattr("app.main._get_user_oauth_scope", lambda user_id: "https://www.googleapis.com/auth/gmail.send")
    monkeypatch.setattr("app.main._get_user_oauth_record", lambda user_id: ("access", "refresh", None))
    monkeypatch.setattr("app.main._ensure_fresh_google_access_token", lambda *args: "fresh-access")
    monkeypatch.setattr("app.main.build", lambda *args, **kwargs: DummyGmailService())

    response = client.post(
        "/api/emails/email-1/reply",
        data={
            "body": "<b>Thanks</b> for the update",
            "to": "sender@example.com",
            "cc": "team@example.com",
            "bcc": "audit@example.com",
            "subject": "Project update",
        },
        files=[
            ("attachments", ("notes.txt", b"first attachment", "text/plain")),
            ("attachments", ("agenda.pdf", b"second attachment", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["attachments"] == 2
    assert sent["body"]["threadId"] == "gmail-thread"
    parsed_message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(sent["body"]["raw"]))
    assert parsed_message["Subject"] == "Re: Project update"
    assert parsed_message["To"] == "sender@example.com"
    assert parsed_message["Cc"] == "team@example.com"
    assert parsed_message["Bcc"] == "audit@example.com"
    assert parsed_message["In-Reply-To"] == "<original@example.com>"
    assert {part.get_filename() for part in parsed_message.iter_attachments()} == {"notes.txt", "agenda.pdf"}


def test_email_body_enrichment_decodes_gmail_text(monkeypatch):
    encoded_body = base64.urlsafe_b64encode(b"Searchable message body").decode("ascii").rstrip("=")

    class DummyMessages:
        def get(self, **kwargs):
            assert kwargs["format"] == "full"
            message = {
                "id": kwargs["id"],
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_body},
                },
            }
            return type("GetRequest", (), {"execute": lambda self: message})()

    class DummyGmailService:
        def users(self):
            return self

        def messages(self):
            return DummyMessages()

    monkeypatch.setattr("app.main._get_user_oauth_record", lambda user_id: ("access", "refresh", None))
    monkeypatch.setattr("app.main._ensure_fresh_google_access_token", lambda *args: "fresh-access")
    monkeypatch.setattr("app.main.build", lambda *args, **kwargs: DummyGmailService())

    emails = _attach_gmail_bodies("user-123", [{"gmail_message_id": "gmail-message"}])

    assert emails[0]["body"] == "Searchable message body"


def test_email_body_enrichment_resolves_inline_cid_images(monkeypatch):
    html_body = '<html><body><img src="cid:logo"></body></html>'
    image_data = base64.urlsafe_b64encode(b"image bytes").decode("ascii")
    encoded_html = base64.urlsafe_b64encode(html_body.encode()).decode("ascii")

    class DummyMessages:
        def get(self, **kwargs):
            message = {
                "id": kwargs["id"],
                "payload": {
                    "mimeType": "multipart/related",
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": encoded_html}},
                        {"mimeType": "image/png", "headers": [{"name": "Content-ID", "value": "<logo>"}], "body": {"data": image_data}},
                    ],
                },
            }
            return type("GetRequest", (), {"execute": lambda self: message})()

    class DummyGmailService:
        def users(self):
            return self

        def messages(self):
            return DummyMessages()

    monkeypatch.setattr("app.main._get_user_oauth_record", lambda user_id: ("access", "refresh", None))
    monkeypatch.setattr("app.main._ensure_fresh_google_access_token", lambda *args: "fresh-access")
    monkeypatch.setattr("app.main.build", lambda *args, **kwargs: DummyGmailService())

    emails = _attach_gmail_bodies("user-123", [{"gmail_message_id": "gmail-message"}])

    assert emails[0]["html_body"] == html_body.replace("cid:logo", f"data:image/png;base64,{image_data}")


def test_reply_rejects_invalid_recipient(monkeypatch):
    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})

    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            class DummyResult:
                def fetchone(self):
                    return ("email-1", "gmail-message", "gmail-thread", "sender@example.com", "Project update")

            return DummyResult()

    class DummyMessages:
        def get(self, **kwargs):
            return type("GetRequest", (), {"execute": lambda self: {"payload": {"headers": []}}})()

    class DummyGmailService:
        def users(self):
            return self

        def messages(self):
            return DummyMessages()

    monkeypatch.setattr("app.main.engine", type("EngineStub", (), {"connect": staticmethod(lambda: DummyConnection())}))
    monkeypatch.setattr("app.main._get_user_oauth_scope", lambda user_id: "https://www.googleapis.com/auth/gmail.send")
    monkeypatch.setattr("app.main._get_user_oauth_record", lambda user_id: ("access", "refresh", None))
    monkeypatch.setattr("app.main._ensure_fresh_google_access_token", lambda *args: "fresh-access")
    monkeypatch.setattr("app.main.build", lambda *args, **kwargs: DummyGmailService())

    response = client.post(
        "/api/emails/email-1/reply",
        data={"body": "Thanks", "to": "not-an-email"},
    )

    assert response.status_code == 400
    assert "valid email" in response.json()["detail"]


def test_reply_rejects_blocked_attachment_type(monkeypatch):
    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})

    response = client.post(
        "/api/emails/email-1/reply",
        data={"body": "See attached"},
        files=[("attachments", ("script.js", b"alert(1)", "application/javascript"))],
    )

    assert response.status_code == 400
    assert "file type" in response.json()["detail"]


def test_emails_requires_authentication():
    response = client.get("/api/emails")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_normalize_token_expiry_handles_datetime_and_iso_string():
    aware_dt = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    iso_value = "2025-01-02T03:04:05Z"

    assert _normalize_token_expiry(aware_dt) == aware_dt
    assert _normalize_token_expiry(iso_value) == aware_dt
    assert _normalize_token_expiry(None) is None


def test_gmail_sync_reaches_google_api_after_expiry_normalization(monkeypatch):
    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            class DummyResult:
                def fetchone(self):
                    return None

            return DummyResult()

    class DummyMessages:
        def list(self, **kwargs):
            return self

        def get(self, **kwargs):
            return self

        def execute(self):
            return {
                "messages": [{"id": "msg-123"}],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Jane Doe <jane@example.com>"},
                        {"name": "Subject", "value": "Hello"},
                        {"name": "Date", "value": "Tue, 02 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "threadId": "thread-123",
                "snippet": "Preview text",
                "internalDate": "1704187200000",
            }

    class DummyGmailService:
        def users(self):
            return self

        def messages(self):
            return DummyMessages()

    monkeypatch.setattr("app.main._require_authenticated_user", lambda request: {"id": "user-123"})
    monkeypatch.setattr("app.main._get_user_oauth_record", lambda user_id: ("access-token", "refresh-token", datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)))
    monkeypatch.setattr("app.main._ensure_fresh_google_access_token", lambda user_id, access_token, refresh_token: "fresh-token")
    monkeypatch.setattr("app.main.build", lambda *args, **kwargs: DummyGmailService())
    monkeypatch.setattr(
        "app.main.engine",
        type(
            "EngineStub",
            (),
            {
                "begin": staticmethod(lambda: DummyConnection()),
                "connect": staticmethod(lambda: DummyConnection()),
            },
        ),
    )

    response = client.post("/api/gmail/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["fetched"] == 1


def test_hiring_email_is_not_defaulted_to_other():
    email_record = {
        "subject": "App Developer at Mastermind Research Technologies",
        "sender": "careers@mastermindresearch.com",
        "sender_name": "Mastermind Careers",
        "snippet": "We are hiring an App Developer. Apply now.",
    }

    result = _build_deterministic_classification(email_record, "We are hiring an App Developer. Join our team. Apply now.")

    assert result["primary_category"] == "OPPORTUNITIES"
    assert result["priority"] == "HIGH"
    assert result["requires_attention"] is True


def test_normalization_and_signals_are_usable_without_gemini():
    email = {
        "subject": "Please confirm your interview availability",
        "sender": "recruiter@company.com",
        "sender_name": "Company Recruiting",
        "snippet": "Please confirm your interview availability for Monday.",
        "payload": {
            "body": {
                "data": "PGRpdiBzdHlsZT0iZm9udC13ZWlnaHQ6IGJvbGQ7Ij5QbGVhc2UgY29uZmlybSB5b3VyIGludGVydmlldyIGF2YWlsYWJpbGl0eSBmb3IgTW9uZGF5LjwvZGl2Pg=="
            }
        },
    }

    normalized = normalize_email_message(email)
    signals = extract_local_signals(normalized)

    assert "Please confirm your interview availability" in normalized["cleaned_text"]
    assert signals["has_reply_request"] is True
    assert signals["has_interview_signal"] is True
    assert signals["has_confirmation_request"] is True
    assert should_use_gemini(signals, normalized["cleaned_text"]) is False


def test_normalization_preserves_original_plain_and_html_bodies():
    original_text = "Café\r\n\r\nSecond line"
    original_html = '<html><body><table><tr><td style="text-align:right">Hello <img src="cid:logo"></td></tr></table></body></html>'
    message = {
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "headers": [{"name": "Content-Type", "value": "text/plain; charset=iso-8859-1"}], "body": {"data": base64.urlsafe_b64encode(original_text.encode("iso-8859-1")).decode()}},
                {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(original_html.encode()).decode()}},
            ],
        },
    }

    normalized = normalize_email_message(message)

    assert normalized["original_body"] == original_text
    assert normalized["html_body"] == original_html


def test_other_is_not_the_default_for_job_like_messages():
    normalized = {
        "cleaned_text": "We are hiring Junior Full-Stack Developers. Apply now and join our team.",
        "subject": "We are hiring Junior Full-Stack Developers",
        "sender": "jobs@example.com",
    }

    signals = extract_local_signals(normalized)
    result = _build_deterministic_classification({"subject": normalized["subject"], "sender": normalized["sender"]}, normalized["cleaned_text"])

    assert signals["has_job_signal"] is True
    assert result["primary_category"] == "OPPORTUNITIES"
    assert result["requires_attention"] is True


def test_validate_classification_accepts_human_readable_fields_and_attention_alias():
    payload = {
        "category": "Action Required",
        "priority": "HIGH",
        "attention": True,
        "action_required": True,
        "action_description": "Confirm the interview timing.",
        "reason": "Direct request requires a response.",
        "confidence": 91.5,
        "waiting_for_response": False,
        "offer_description": "Interview slot",
    }

    result = validate_classification(payload)

    assert result is not None
    assert result["category"] == "ACTION_REQUIRED"
    assert result["attention"] is True
    assert result["priority"] == "HIGH"
    assert result["action_required"] is True


def test_validate_classification_reclassifies_other_when_action_signals_exist():
    payload = {
        "category": "Other",
        "priority": "LOW",
        "attention": False,
        "action_required": False,
        "action_description": "Please reply to confirm your interview.",
        "reason": "A direct reply request should be treated as actionable.",
        "confidence": 88.0,
        "waiting_for_response": False,
        "offer_description": "",
    }

    result = validate_classification(payload)

    assert result is not None
    assert result["category"] == "ACTION_REQUIRED"
    assert result["attention"] is True
    assert result["priority"] == "HIGH"


def test_attention_policy_keeps_opportunity_medium_without_urgent_action():
    result = _apply_attention_policy(
        {
            "category": "Opportunities",
            "primary_category": "Opportunities",
            "action_required": False,
            "opportunity_description": "Relevant job opportunity.",
        },
        "A new software engineering role is available.",
    )

    assert result["priority"] == "MEDIUM"
    assert result["attention"] is False
    assert result["action_required"] is False


def test_attention_policy_keeps_promotions_low_and_calm():
    result = _apply_attention_policy(
        {
            "category": "Other",
            "primary_category": "Other",
            "action_required": False,
        },
        "Special offer and promotion. Unsubscribe anytime.",
    )

    assert result["priority"] == "LOW"
    assert result["attention"] is False
    assert result["action_required"] is False


def test_attention_policy_does_not_make_ordinary_events_high():
    result = _apply_attention_policy(
        {
            "category": "Events & Invitations",
            "primary_category": "Events & Invitations",
            "action_required": False,
        },
        "Join our community webinar next month.",
    )

    assert result["priority"] == "LOW"
    assert result["attention"] is False
    assert result["action_required"] is False


def test_attention_policy_escalates_genuine_security_alert():
    result = _apply_attention_policy(
        {
            "category": "Important Alerts",
            "primary_category": "Important Alerts",
            "action_required": True,
        },
        "Security alert: suspicious login detected on your account.",
    )

    assert result["priority"] == "HIGH"
    assert result["attention"] is True
    assert result["action_required"] is True

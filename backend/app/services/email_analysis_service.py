import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.app.services.email_normalization_service import normalize_email_message
from backend.app.services.email_signal_service import extract_local_signals
from backend.database import engine

APPROVED_CATEGORIES = [
    "ACTION_REQUIRED",
    "OPPORTUNITIES",
    "EVENTS",
    "ALERTS",
    "INFORMATION",
]

CATEGORY_BOUNDARIES = {
    "ACTION_REQUIRED": {
        "belongs": "A concrete user action is the main purpose of the message.",
        "excludes": "A deadline, event, or opportunity mentioned only as context.",
        "strong_signals": ["reply request", "confirmation", "submission", "verification", "registration"],
        "competes_with": ["EVENTS", "OPPORTUNITIES"],
        "tie_break": "Wins over Events when attendance or registration needs confirmation; loses to Opportunities when the opportunity itself is the purpose.",
    },
    "OPPORTUNITIES": {
        "belongs": "A job, internship, scholarship, career, or professional opportunity is the main purpose.",
        "excludes": "Generic educational or promotional content without a concrete opportunity.",
        "strong_signals": ["role", "hiring", "application", "scholarship", "shortlisted"],
        "competes_with": ["ACTION_REQUIRED", "INFORMATION"],
        "tie_break": "Wins over application requests and deadlines; those remain secondary attributes.",
    },
    "EVENTS": {
        "belongs": "The message is centered on a real meeting, appointment, interview, invitation, or scheduled event.",
        "excludes": "A date or event word that is incidental to another purpose.",
        "strong_signals": ["calendar invitation", "meeting", "appointment", "interview", "RSVP"],
        "competes_with": ["ACTION_REQUIRED", "OPPORTUNITIES"],
        "tie_break": "Loses to a concrete confirmation or response request and loses to an opportunity-centered interview.",
    },
    "ALERTS": {
        "belongs": "A consequential account, security, financial, billing, access, or service-state issue needs attention.",
        "excludes": "Routine statements, generic bank advisories, pricing, or ordinary product announcements.",
        "strong_signals": ["suspicious login", "payment failed", "account paused", "unauthorized access", "service outage"],
        "competes_with": ["ACTION_REQUIRED", "INFORMATION"],
        "tie_break": "Wins when the account or security consequence is meaningful, even when the message asks for verification.",
    },
    "INFORMATION": {
        "belongs": "The message informs, announces, teaches, reports, or promotes without a concrete user action.",
        "excludes": "A real opportunity, consequential alert, or explicit request for the user.",
        "strong_signals": ["newsletter", "announcement", "report", "digest", "promotion", "advisory"],
        "competes_with": ["OPPORTUNITIES"],
        "tie_break": "Use when the message has a recognizable informational purpose but no stronger primary intent.",
    },
}

REQUIRED_CLASSIFICATION_FIELDS = {
    "category",
    "primary_category",
    "attention",
    "requires_attention",
    "priority",
    "action_required",
    "action_description",
    "deadline",
    "event_date",
    "waiting_for_response",
    "awaiting_response",
    "offer_description",
    "opportunity_description",
    "reason",
    "confidence",
    "can_reply",
    "reply_reason",
    "secondary_signals",
}

PRIORITY_LEVELS = {"URGENT", "HIGH", "MEDIUM", "LOW"}
CLASSIFIER_VERSION = "intent-v4"
GEMINI_CONFIDENCE_THRESHOLD = 72.0
GEMINI_MARGIN_THRESHOLD = 14.0


def should_use_gemini(signals: dict[str, Any], email_text: str, deterministic: dict[str, Any] | None = None) -> bool:
    if not email_text or not email_text.strip():
        return False
    if deterministic is None:
        return False

    if signals.get("conflicting_intents"):
        return True
    if (deterministic or {}).get("classification_margin", 0.0) < GEMINI_MARGIN_THRESHOLD:
        return True
    return float((deterministic or {}).get("confidence", 0.0)) < GEMINI_CONFIDENCE_THRESHOLD


def ensure_email_analysis_schema() -> None:
    required_columns = {
        "category": "VARCHAR(100)",
        "primary_category": "VARCHAR(100)",
        "attention": "BOOLEAN",
        "requires_attention": "BOOLEAN",
        "priority": "VARCHAR(20)",
        "action_required": "BOOLEAN",
        "action_description": "TEXT",
        "deadline": "TIMESTAMPTZ",
        "event_date": "TIMESTAMPTZ",
        "waiting_for_response": "BOOLEAN",
        "awaiting_response": "BOOLEAN",
        "offer_description": "TEXT",
        "opportunity_description": "TEXT",
        "reason": "TEXT",
        "confidence": "NUMERIC(5,2)",
        "can_reply": "BOOLEAN",
        "reply_reason": "TEXT",
        "content_hash": "VARCHAR(64)",
        "classifier_version": "VARCHAR(50)",
        "gemini_used": "BOOLEAN",
        "secondary_signals": "JSONB",
    }

    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            connection.execute(
                text(
                    f"""
                    ALTER TABLE email_analysis
                    ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                    """
                )
            )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_email_analysis_unique_email
                ON email_analysis(email_id)
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE email_analysis
                SET category = 'INFORMATION',
                    primary_category = 'INFORMATION'
                WHERE regexp_replace(lower(COALESCE(category, primary_category)), '[^a-z]', '', 'g') = 'lowpriority'
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE email_analysis
                SET category = CASE regexp_replace(lower(COALESCE(category, primary_category)), '[^a-z&]', '', 'g')
                    WHEN 'upcomingdeadlines' THEN 'ACTION_REQUIRED'
                    WHEN 'events&invitations' THEN 'EVENTS'
                    WHEN 'awaitingresponse' THEN 'ACTION_REQUIRED'
                    WHEN 'importantalerts' THEN 'ALERTS'
                    WHEN 'updates' THEN 'INFORMATION'
                    WHEN 'other' THEN 'INFORMATION'
                    ELSE category
                END,
                    primary_category = CASE regexp_replace(lower(COALESCE(primary_category, category)), '[^a-z&]', '', 'g')
                    WHEN 'upcomingdeadlines' THEN 'ACTION_REQUIRED'
                    WHEN 'events&invitations' THEN 'EVENTS'
                    WHEN 'awaitingresponse' THEN 'ACTION_REQUIRED'
                    WHEN 'importantalerts' THEN 'ALERTS'
                    WHEN 'updates' THEN 'INFORMATION'
                    WHEN 'other' THEN 'INFORMATION'
                    ELSE primary_category
                END
                WHERE category IS NOT NULL OR primary_category IS NOT NULL
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE email_analysis
                SET category = COALESCE(category, primary_category),
                    primary_category = COALESCE(primary_category, category),
                    attention = COALESCE(attention, requires_attention),
                    requires_attention = COALESCE(requires_attention, attention),
                    waiting_for_response = COALESCE(waiting_for_response, awaiting_response),
                    awaiting_response = COALESCE(awaiting_response, waiting_for_response),
                    offer_description = COALESCE(offer_description, opportunity_description),
                    opportunity_description = COALESCE(opportunity_description, offer_description)
                WHERE email_id IS NOT NULL
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE email_analysis
                SET category = CASE regexp_replace(lower(COALESCE(category, primary_category, 'information')), '[^a-z]', '', 'g')
                    WHEN 'actionrequired' THEN 'ACTION_REQUIRED'
                    WHEN 'upcomingdeadlines' THEN 'ACTION_REQUIRED'
                    WHEN 'events' THEN 'EVENTS'
                    WHEN 'eventsinvitations' THEN 'EVENTS'
                    WHEN 'awaitingresponse' THEN 'ACTION_REQUIRED'
                    WHEN 'opportunities' THEN 'OPPORTUNITIES'
                    WHEN 'importantalerts' THEN 'ALERTS'
                    WHEN 'accountsecurity' THEN 'ALERTS'
                    WHEN 'alerts' THEN 'ALERTS'
                    WHEN 'updates' THEN 'INFORMATION'
                    WHEN 'informational' THEN 'INFORMATION'
                    WHEN 'information' THEN 'INFORMATION'
                    WHEN 'other' THEN 'INFORMATION'
                    ELSE 'INFORMATION'
                END,
                    primary_category = CASE regexp_replace(lower(COALESCE(primary_category, category, 'information')), '[^a-z]', '', 'g')
                    WHEN 'actionrequired' THEN 'ACTION_REQUIRED'
                    WHEN 'upcomingdeadlines' THEN 'ACTION_REQUIRED'
                    WHEN 'events' THEN 'EVENTS'
                    WHEN 'eventsinvitations' THEN 'EVENTS'
                    WHEN 'awaitingresponse' THEN 'ACTION_REQUIRED'
                    WHEN 'opportunities' THEN 'OPPORTUNITIES'
                    WHEN 'importantalerts' THEN 'ALERTS'
                    WHEN 'accountsecurity' THEN 'ALERTS'
                    WHEN 'alerts' THEN 'ALERTS'
                    WHEN 'updates' THEN 'INFORMATION'
                    WHEN 'informational' THEN 'INFORMATION'
                    WHEN 'information' THEN 'INFORMATION'
                    WHEN 'other' THEN 'INFORMATION'
                    ELSE 'INFORMATION'
                END
                WHERE email_id IS NOT NULL
                """
            )
        )


ensure_email_analysis_schema()


def _normalize_category(value: Any) -> str:
    raw_text = str(value or "").strip()
    if not raw_text:
        return "INFORMATION"

    normalized = re.sub(r"[^a-z0-9]+", " ", raw_text.lower()).strip()
    lookup = {
        "action required": "ACTION_REQUIRED",
        "action requireds": "ACTION_REQUIRED",
        "upcoming deadlines": "ACTION_REQUIRED",
        "upcoming deadline": "ACTION_REQUIRED",
        "events invitations": "EVENTS",
        "event invitations": "EVENTS",
        "events and invitations": "EVENTS",
        "events": "EVENTS",
        "awaiting response": "ACTION_REQUIRED",
        "opportunities": "OPPORTUNITIES",
        "important alerts": "ALERTS",
        "account security": "ALERTS",
        "alerts": "ALERTS",
        "updates": "INFORMATION",
        "informational": "INFORMATION",
        "information": "INFORMATION",
        "other": "INFORMATION",
    }
    return lookup.get(normalized, "INFORMATION")


def _normalize_priority(value: Any) -> str:
    raw_text = str(value or "").strip().upper()
    return raw_text if raw_text in PRIORITY_LEVELS else "MEDIUM"

def _normalize_attention(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "attention", "required"}
    return bool(value)


def _coerce_datetime(value: Any) -> str | None:
    if value in (None, "", "null"):
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text_value = value.strip()
        if text_value.endswith("Z"):
            text_value = text_value[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text_value)
        except ValueError:
            return value
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).isoformat()


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _email_content_hash(email_record: dict[str, Any], email_text: str) -> str:
    content = "\n".join(
        str(email_record.get(field) or "").strip()
        for field in ["sender", "sender_name", "subject", "snippet"]
    ) + "\n" + (email_text or "").strip()
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def _extract_email_text(message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    parts = payload.get("parts") or []
    text_chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime_type = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            try:
                raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                text_chunks.append(raw.decode("utf-8", errors="replace"))
            except Exception:
                pass

        if part.get("parts"):
            for child in part["parts"]:
                walk(child)

        if mime_type.startswith("text/") and not data:
            attachment_data = body.get("data")
            if attachment_data:
                try:
                    raw = base64.urlsafe_b64decode(attachment_data + "=" * (-len(attachment_data) % 4))
                    text_chunks.append(raw.decode("utf-8", errors="replace"))
                except Exception:
                    pass

    for part in parts:
        walk(part)

    if not text_chunks:
        body = payload.get("body", {})
        data = body.get("data")
        if data:
            try:
                raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                text_chunks.append(raw.decode("utf-8", errors="replace"))
            except Exception:
                pass

    combined = "\n".join(text_chunks)
    if not combined:
        combined = message.get("snippet") or ""

    return re.sub(r"\s+", " ", combined).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    for keyword in keywords:
        normalized_keyword = re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip()
        keyword_pattern = re.escape(normalized_keyword).replace(r"\ ", r"\s+")
        if re.search(rf"\b{keyword_pattern}\b", normalized):
            return True
    return False


def _has_action_intent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:please|kindly)\s+(?:reply|respond|confirm|submit|approve|register|provide|complete|verify|upload|share|send|apply)\b"
            r"|\b(?:reply|respond|confirm|submit|approve|register|provide|complete|verify|upload|share)\s+(?:by|your|the|this|that|details|information|form|document)\b"
            r"|\b(?:can|could|would)\s+you\s+(?:please\s+)?(?:reply|respond|confirm|provide|send|submit|complete|verify)\b"
            r"|\b(?:action required|response required|your response is needed|confirmation required|take action|accept|decline|apply now)\b",
            text.lower(),
        )
    )


def _has_event_intent(subject: str, text: str) -> bool:
    combined = f"{subject} {text}".lower()
    has_event_anchor = bool(
        re.search(
            r"\b(?:meeting|appointment|webinar|conference|interview|workshop|seminar|meetup|calendar\s+(?:invite|invitation)|invitation|invited|rsvp|registration)\b",
            combined,
        )
    )
    has_event_context = bool(
        re.search(
            r"\b(?:agenda|attendees?|attend|join\s+(?:us|the)|location|venue|calendar|scheduled\s+(?:for|on|at)|(?:on|at)\s+(?:mon|tue|wed|thu|fri|sat|sun)|confirm\s+(?:your\s+)?(?:attendance|availability)|register\s+for|registration\s+(?:is\s+)?(?:open|required|available)|event\s+(?:schedule|registration)|tomorrow|today|next\s+(?:week|month)|invitation)\b",
            combined,
        )
    )
    return has_event_anchor and has_event_context


def _event_requires_action_primary(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(?:please\s+)?(?:confirm|respond|reply)\s+(?:your\s+)?(?:interview\s+)?availability\b"
            r"|\bplease\s+(?:confirm|respond|reply)\b.*\b(?:interview|appointment|meeting)\b",
            lowered,
        )
    )


def _has_deadline_intent(text: str) -> bool:
    lowered = text.lower()
    has_deadline_phrase = bool(
        re.search(
            r"\b(?:deadline|due\s+(?:by|on)|submit\s+by|no\s+later\s+than|expires?\s+(?:on|in|by)?|expiration\s+date|closing\s+date|final\s+date|application\s+deadline|application\s+closes?|registration\s+closes?|valid\s+until|last\s+date)\b",
            lowered,
        )
    )
    has_time_anchor = bool(
        re.search(
            r"\b(?:today|tomorrow|this\s+(?:week|month)|next\s+(?:week|month)|within\s+\d+\s+days?|by\s+\w+\s+\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
            lowered,
        )
    )
    return has_deadline_phrase and has_time_anchor


def _has_opportunity_intent(text: str) -> bool:
    lowered = text.lower()
    opportunity_anchor = bool(
        re.search(
            r"\b(?:job|jobs|job\s+alert|role|position|opening|vacancy|intern(?:ship)?|scholarship|fellowship|career|career\s+opportunity|employment\s+opportunity|hiring|recruit(?:ment|er|ing))\b",
            lowered,
        )
    )
    opportunity_context = bool(
        re.search(
            r"\b(?:apply|application|join\s+our\s+team|salary|responsibilities|qualifications|job\s+description|job\s+alert|software\s+engineer|remote|roles?\s+(?:available|open)|opportunity\s+to|available|open|selected|shortlisted|scholarship|fellowship)\b",
            lowered,
        )
    )
    return opportunity_anchor and opportunity_context


def _has_awaiting_response_intent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:awaiting\s+(?:your|a)\s+response|waiting\s+for\s+your\s+response|response\s+pending|pending\s+response|we\s+will\s+(?:get\s+back|contact\s+you|follow\s+up|respond|reply)|we['’]ll\s+contact\s+you|(?:we\s+)?received\s+your\s+(?:job\s+)?application(?:\s+and\s+will\s+get\s+back)?|your\s+application\s+is\s+(?:under\s+review|being\s+reviewed)|waiting\s+to\s+hear\s+from\s+you|awaiting\s+(?:our|their)\s+response|we\s+are\s+reviewing)\b",
            text.lower(),
        )
    )


def _has_consequential_alert_intent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:security\s+(?:alert|warning|incident|activity)|suspicious\s+(?:login|activity)|unauthorized\s+login|account\s+(?:was\s+)?(?:compromised|warning|locked|suspended|accessed)|password\s+(?:changed|reset|security)|payment\s+(?:failed|declined)|bank(?:ing)?\s+(?:alert|notification|activity)|debit\s+card|credit\s+card|fraud\s+alert|bank\s+alert|billing\s+issue|service\s+(?:disruption|outage|pause|paused|pausing)|(?:account|subscription|project)\s+(?:will\s+be\s+|is\s+going\s+to\s+be\s+)?paused|explicit\s+grants?|access\s+(?:review|change|from\s+a\s+new\s+device)|critical\s+account\s+notification|login\s+from\s+a\s+new\s+device)\b",
            text.lower(),
        )
    )


def _is_marketing_or_newsletter(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:marketing|advertisement|advertising|newsletter|unsubscribe|special\s+offer|discount|ad\s+credit|improve\s+your\s+(?:profile|ranking|reach)|try\s+(?:google\s+)?ads|promotional|limited\s+time|last\s+chance\s+savings|frameworks?\s+for\s+your\s+next|terms\s+of\s+service|community\s+guidelines|advisory|announcement|statement\s+of\s+account|performance\s+report|pricing|exclusive\s+access|skill[- ]building|digest|offers?)\b",
            text.lower(),
        )
    )


def _looks_like_real_date_candidate(value: str) -> bool:
    if not value or len(value) > 80:
        return False

    candidate = value.strip()
    if not re.search(r"\d", candidate) and not re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\b", candidate, re.I):
        return False

    date_patterns = [
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        r"\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*,?\s*\d{2,4}",
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}",
    ]
    return any(re.search(pattern, candidate, re.I) for pattern in date_patterns)


def _extract_deadline_or_event_date(text: str) -> tuple[str | None, str | None]:
    lowered = (text or "").lower()
    date_value = None
    event_value = None

    for pattern in [
        r"(?:due by|deadline|submit by|no later than|before|expires? on|expires?|expiration|closing date|final date|last date|application deadline)\s*[:\-]?\s*([a-z0-9, /-]{4,})",
        r"(?:on|at)\s+([a-z]+\s+\d{1,2},?\s+\d{4})",
    ]:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(1).strip()
            if _looks_like_real_date_candidate(candidate):
                date_value = candidate
                break

    if not date_value:
        event_match = re.search(r"(?:meeting|interview|appointment|webinar|conference|event|invitation|scheduled|calendar invitation|assessment)\s*(?:on|at|for)?\s*([a-z0-9, /-]{4,})", lowered)
        if event_match:
            candidate = event_match.group(1).strip()
            if _looks_like_real_date_candidate(candidate):
                event_value = candidate

    return date_value, event_value


def _build_legacy_deterministic_classification(email_record: dict[str, Any], email_text: str) -> dict[str, Any]:
    subject = (email_record.get("subject") or "").strip()
    sender = (email_record.get("sender") or "").strip()
    sender_name = (email_record.get("sender_name") or "").strip()
    snippet = (email_record.get("snippet") or "").strip()
    text = "\n".join(filter(None, [subject, sender_name, sender, email_text, snippet])).strip()
    lowered = text.lower()

    category = "OTHER"
    requires_attention = False
    action_required = False
    awaiting_response = False
    opportunity_description = ""
    action_description = "Review this email for context."
    deadline = None
    event_date = None
    can_reply = False
    reply_reason = "This message is informational and does not require a reply."
    reason = "Classification based on the actual email content and intent."
    priority = "LOW"

    opportunity_keywords = [
        "hiring", "recruitment", "join our team", "job opening", "position available", "vacancy",
        "internship", "interview opportunity", "career opportunity", "job opportunity",
        "employment opportunity", "we are hiring", "we are recruiting", "apply now",
        "application", "shortlisted", "selected", "you have been shortlisted",
        "role available", "available position", "open position", "opportunity to join",
        "we're hiring", "positions available", "software engineer intern", "app developer"
    ]
    action_keywords = [
        "please reply", "please respond", "kindly reply", "kindly confirm", "let me know",
        "confirm", "submit", "upload", "complete", "provide", "send us", "register",
        "verify", "approve", "accept", "choose", "rsvp", "apply", "review and respond"
    ]
    deadline_keywords = [
        "due by", "deadline", "submit by", "before", "no later than", "expires", "expiration",
        "final date", "last date", "closing date", "closing soon", "application deadline"
    ]
    event_keywords = [
        "interview", "meeting", "appointment", "webinar", "conference", "event", "invitation",
        "rsvp", "scheduled", "calendar invite", "calendar invitation", "assessment"
    ]
    awaiting_keywords = [
        "we have received your application", "we will get back to you", "we will contact you shortly",
        "your application is under review", "under review", "will review your application",
        "reviewing your application", "awaiting decision", "we are reviewing", "we will follow up"
    ]
    alert_keywords = [
        "security alert", "suspicious login", "password changed", "account changes",
        "payment failed", "payment failure", "important account notification", "service disruption",
        "critical system notification", "account compromised", "unauthorized login", "verification code",
        "2fa", "two-factor", "security update"
    ]
    update_keywords = [
        "weekly update", "monthly update", "product update", "customer update", "here is our update",
        "release notes", "company update", "new feature", "service update", "status update",
        "newsletter", "blog update", "performance report", "pricing update", "cloud pricing", "digest", "terms of service", "community guidelines", "framework", "frameworks", "5 rules for", "how to", "guide", "educational"
    ]
    other_keywords = [
        "unsubscribe", "special offer", "limited time", "promotion", "marketing", "sale",
        "flash sale", "trial ended", "new feature", "promo", "advertisement"
    ]

    deadline_candidate, event_candidate = _extract_deadline_or_event_date(text)
    if deadline_candidate:
        deadline = deadline_candidate
    if event_candidate:
        event_date = event_candidate

    if _has_consequential_alert_intent(text):
        category = "IMPORTANT_ALERTS"
        requires_attention = True
        action_required = True
        action_description = "Address the security, account, or service issue immediately."
        can_reply = False
        reply_reason = "This is a critical account or security alert, not a conversational message."
        priority = "URGENT" if any(word in lowered for word in ["compromised", "suspicious", "unauthorized", "payment failed", "service disruption", "critical"]) else "HIGH"
        reason = "The email indicates a security, account, or service issue requiring prompt attention."
    elif (
        _has_deadline_intent(text)
        and not _has_opportunity_intent(text)
        and not _has_event_intent(subject, text)
        and not _has_action_intent(text)
    ):
        category = "UPCOMING_DEADLINES"
        requires_attention = True
        action_required = True
        action_description = "Complete the required task or submission before the stated deadline."
        can_reply = True
        reply_reason = "The email includes a deadline or required action with a time-sensitive follow-up."
        priority = "URGENT" if any(word in lowered for word in ["expires", "expiration", "urgent", "immediately", "today", "tomorrow"]) else "HIGH"
        reason = "The message contains an explicit or strong implied deadline requiring attention."
    elif _has_opportunity_intent(text):
        category = "OPPORTUNITIES"
        requires_attention = True
        action_required = bool(_contains_any(lowered, ["apply now", "apply", "interview", "shortlisted", "selected", "join our team", "position available"]))
        opportunity_description = "This appears to be a career or business opportunity that may require a response or follow-up."
        action_description = "Review the opportunity and decide whether to pursue the next step."
        can_reply = action_required or any(word in lowered for word in ["interview", "call", "next steps"]) or "selected" in lowered
        reply_reason = "This email presents a possible opportunity or next step that may require a response."
        priority = "HIGH" if any(word in lowered for word in ["apply now", "interview", "shortlisted", "selected", "join our team", "hiring", "position available"]) else "MEDIUM"
        reason = "The email presents a hiring, recruitment, or other opportunity that needs attention based on content and intent."
    elif _has_awaiting_response_intent(text):
        category = "AWAITING_RESPONSE"
        requires_attention = False
        action_required = False
        awaiting_response = True
        action_description = "Wait for the sender to follow up or provide the next update."
        can_reply = False
        reply_reason = "The sender is indicating they will respond or review the matter, so no immediate action is required from the user."
        priority = "LOW"
        reason = "The sender indicates they will respond or review the matter rather than asking the user to act."
    elif _has_event_intent(subject, text) and not _event_requires_action_primary(text):
        category = "EVENTS_INVITATIONS"
        requires_attention = True
        action_required = bool(_contains_any(lowered, ["rsvp", "please confirm", "confirm your attendance", "register", "join us"]))
        action_description = "Review the event details and confirm your attendance if needed."
        can_reply = action_required or any(word in lowered for word in ["invitation", "meeting", "interview", "appointment", "calendar"])
        reply_reason = "This email is about an event, meeting, or invitation that may require confirmation."
        priority = "HIGH" if any(word in lowered for word in ["interview", "rsvp", "important meeting", "final event"]) else "MEDIUM"
        reason = "The content is centered on a meeting, invitation, or event with a possible response requirement."
    elif _has_action_intent(text) and not _is_marketing_or_newsletter(text):
        category = "ACTION_REQUIRED"
        requires_attention = True
        action_required = True
        action_description = "Respond to the request or complete the requested action in the message."
        can_reply = True
        reply_reason = "The sender is explicitly asking the user to respond, confirm, or take action."
        priority = "HIGH" if any(word in lowered for word in ["please respond", "please reply", "urgent", "submit", "verify", "approve", "accept"]) else "MEDIUM"
        reason = "The email contains a direct request for the user to reply, confirm, submit, or complete something."
    elif _contains_any(text, update_keywords) and (not _has_action_intent(text) or _is_marketing_or_newsletter(text)):
        category = "UPDATES"
        requires_attention = False
        action_required = False
        action_description = "Review the update if it is relevant to your priorities."
        can_reply = False
        reply_reason = "This is informational and does not appear to require a response."
        priority = "LOW"
        reason = "The email is primarily an informational update and does not require immediate action."
    elif _contains_any(text, other_keywords):
        category = "OTHER"
        requires_attention = False
        action_required = False
        action_description = "No immediate action is required."
        can_reply = False
        reply_reason = "This looks like promotional or low-value content without any meaningful action requirement."
        priority = "LOW"
        reason = "The email appears to be generic promotional or low-value content."

    return {
        "primary_category": category,
        "requires_attention": bool(requires_attention),
        "priority": priority,
        "action_required": bool(action_required),
        "action_description": action_description,
        "deadline": deadline,
        "event_date": event_date,
        "awaiting_response": bool(awaiting_response),
        "opportunity_description": opportunity_description,
        "reason": reason,
        "confidence": 0.92,
        "can_reply": bool(can_reply),
        "reply_reason": reply_reason,
    }


def _build_semantic_signals(email_record: dict[str, Any], email_text: str) -> dict[str, Any]:
    subject = str(email_record.get("subject") or "").strip()
    sender = str(email_record.get("sender") or "").strip().lower()
    sender_domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""
    context = "\n".join(
        filter(
            None,
            [subject, str(email_record.get("sender_name") or ""), sender, str(email_record.get("snippet") or ""), email_text],
        )
    )
    deadline, event_date = _extract_deadline_or_event_date(context)
    has_informational = _is_marketing_or_newsletter(context) or _contains_any(
        context,
        ["newsletter", "weekly update", "product update", "release notes", "announcement", "digest", "guide", "how to", "course", "class", "lesson", "learning", "skill-building"],
    )
    strong_action = _contains_any(
        context,
        ["please reply", "please respond", "please confirm", "confirm your", "submit your", "upload your", "register now", "rsvp", "take action", "action required", "response required", "apply now", "verify your"],
    )
    has_action = _has_action_intent(context) and (not has_informational or strong_action)
    has_event = _has_event_intent(subject, context)
    has_opportunity = _has_opportunity_intent(context) or bool(
        re.search(r"(?:indeed|linkedin|unstop|jobalert|recruit).+@|(?:indeed|linkedin|unstop|jobalert|recruit)", sender)
        and re.search(r"\b(?:job|jobs|hiring|developer|engineer|intern|career|role|position)\b", subject.lower())
    )
    has_account_alert = _has_consequential_alert_intent(context)
    has_waiting = _has_awaiting_response_intent(context)
    urgent = _contains_any(context, ["urgent", "immediately", "today", "tomorrow", "expires", "expiring", "critical"])
    opportunity_type = next(
        (kind for kind, words in {
            "scholarship": ["scholarship", "grant"],
            "internship": ["internship", "intern"],
            "job": ["job", "hiring", "role", "position", "developer", "engineer"],
            "freelance": ["freelance", "contract work"],
            "competition": ["competition", "contest", "challenge"],
            "business": ["business opportunity", "partnership"],
        }.items() if _contains_any(context, words)),
        None,
    )
    content_type = next(
        (kind for kind, words in {
            "course": ["course", "class", "lesson"],
            "newsletter": ["newsletter", "digest"],
            "promotion": ["sale", "discount", "offer", "limited time"],
            "educational": ["guide", "tutorial", "how to", "framework"],
        }.items() if _contains_any(context, words)),
        None,
    )
    alert_type = next(
        (kind for kind, words in {
            "security": ["security", "suspicious", "unauthorized", "accessed", "login"],
            "financial": ["payment", "bank", "debit", "credit", "billing", "transaction"],
            "account": ["account", "password", "grants", "access"],
            "service": ["service", "outage", "paused", "disruption"],
        }.items() if _contains_any(context, words)),
        None,
    )
    candidates: dict[str, float] = {
        "ACTION_REQUIRED": 1.0,
        "OPPORTUNITIES": 1.0,
        "EVENTS": 1.0,
        "ALERTS": 1.0,
        "INFORMATION": 1.0 if has_informational else 0.0,
    }

    if has_account_alert:
        candidates["ALERTS"] += 11
    if has_opportunity:
        candidates["OPPORTUNITIES"] += 12
    if has_event:
        candidates["EVENTS"] += 10
    if has_action:
        candidates["ACTION_REQUIRED"] += 9
    if has_informational and not strong_action:
        candidates["INFORMATION"] += 5
    if has_waiting and not has_action and not has_opportunity:
        candidates["INFORMATION"] += 2
    if not any([has_account_alert, has_opportunity, has_event, has_action, deadline, has_informational]):
        candidates["INFORMATION"] += 3

    ordered = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
    category, top_score = ordered[0]
    margin = top_score - ordered[1][1]
    evidence_count = sum(bool(value) for value in [has_account_alert, has_opportunity, has_event, has_action, deadline, has_informational])
    confidence = min(98.0, 62.0 + (margin * 2.5) + (evidence_count * 4.0))
    if category == "INFORMATION" and evidence_count == 0:
        confidence = 58.0

    action_required = has_action and category in {"ACTION_REQUIRED", "OPPORTUNITIES", "EVENTS", "ALERTS"}
    attention = action_required or (category == "ALERTS" and has_account_alert)
    priority = "URGENT" if has_account_alert and urgent else "HIGH" if action_required and (urgent or category == "OPPORTUNITIES") else "MEDIUM" if attention else "LOW"
    secondary_signals = {
        "sender_domain": sender_domain,
        "has_deadline": bool(deadline),
        "has_event": has_event,
        "has_opportunity": has_opportunity,
        "has_action_request": has_action,
        "awaiting_response": has_waiting,
        "opportunity_type": opportunity_type,
        "content_type": content_type,
        "alert_type": alert_type,
        "informational": has_informational,
        "promotional": bool(_contains_any(context, ["sale", "discount", "special offer", "unsubscribe", "limited time"])),
        "urgent": urgent,
        "detected_dates": re.findall(
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            context,
            flags=re.I,
        ),
        "candidate_scores": {key: round(value, 2) for key, value in candidates.items()},
    }
    return {
        "category": category,
        "primary_category": category,
        "attention": attention,
        "requires_attention": attention,
        "priority": priority,
        "action_required": action_required,
        "action_description": "Respond or complete the requested action." if action_required else "Review this message if it is relevant.",
        "deadline": deadline,
        "event_date": event_date,
        "waiting_for_response": has_waiting,
        "awaiting_response": has_waiting,
        "offer_description": "This message presents an opportunity." if has_opportunity else "",
        "opportunity_description": "This message presents an opportunity." if has_opportunity else "",
        "reason": f"Primary intent is {category}; secondary signals are retained separately.",
        "confidence": round(confidence, 2),
        "classification_margin": round(margin, 2),
        "can_reply": bool(has_action or (category == "OPPORTUNITIES" and has_opportunity)),
        "reply_reason": "The message contains a request or a possible next step." if has_action or has_opportunity else "No reply is indicated by the message.",
        "secondary_signals": secondary_signals,
    }


def _build_deterministic_classification(email_record: dict[str, Any], email_text: str) -> dict[str, Any]:
    return _build_semantic_signals(email_record, email_text)


def _extract_json_from_text(response_text: str) -> dict[str, Any]:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _call_gemini_for_classification(
    email_record: dict[str, Any],
    email_text: str,
    signals: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(f"[ANALYSIS] Gemini not configured for email_id={email_record.get('id')} message_id={email_record.get('gmail_message_id')}")
        return None

    try:
        print(f"[ANALYSIS] Gemini called for email_id={email_record.get('id')} message_id={email_record.get('gmail_message_id')}")
        from google import generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
        prompt = f"""
You are an email triage classifier.
Classify the message by its primary purpose, not isolated keywords.

Use exactly one of these categories only:
1. ACTION_REQUIRED
2. OPPORTUNITIES
3. EVENTS
4. ALERTS
5. INFORMATION

Rules:
- Choose a category only when the whole message supports its intent; a single word such as "event", "deadline", "response", or "offer" is not sufficient.
- ACTION_REQUIRED requires a direct request for the user to reply, confirm, submit, verify, approve, pay, provide information, or complete a required step.
- OPPORTUNITIES requires a genuine career, professional, financial, scholarship, competition, freelance, or business opportunity. Courses, learning resources, and ordinary promotions are INFORMATION.
- EVENTS requires a real scheduled event, appointment, meeting, interview, webinar, conference, exam, or similar occurrence. Confirmation can remain an action_required secondary attribute.
- ALERTS requires a meaningful existing-account, service, financial-activity, security, login, payment, or system-condition notification, not merely words like important or warning.
- INFORMATION covers educational content, courses, newsletters, updates, announcements, and promotions without a stronger primary purpose.
- Deadlines and awaiting-response state are secondary attributes, never primary categories.
- Choose INFORMATION when context is insufficient; never invent a sixth category.
- Priority must be independent from category and based on urgency and impact.
- Use the subject, sender, sender name, snippet, and decoded email body.
Return strict JSON only, with these keys and no extras:
{{
    "category": "one of the 5 category names above",
    "confidence": 0.0-100.0,
    "reason": "clear explanation based on the whole message",
    "attention": true|false,
    "priority": "URGENT|HIGH|MEDIUM|LOW",
    "action_required": true|false,
    "deadline": "ISO date/time or null",
    "event_date": "ISO date/time or null",
    "secondary_signals": {{"awaiting_response": true|false, "has_deadline": true|false, "has_event": true|false, "has_opportunity": true|false, "promotional": true|false}}
}}

Email subject: {email_record.get('subject') or ''}
Email sender: {email_record.get('sender') or ''}
Email sender name: {email_record.get('sender_name') or ''}
Email snippet: {email_record.get('snippet') or ''}
Email content: {email_text}
Extracted signals: {json.dumps(signals or {}, sort_keys=True, default=str)}
Category boundaries: {json.dumps(CATEGORY_BOUNDARIES, sort_keys=True)}
"""
        response = model.generate_content(prompt, request_options={"timeout": 15})
        payload = _extract_json_from_text(response.text)
        validated = validate_classification(payload)
        if validated and validated["confidence"] >= GEMINI_CONFIDENCE_THRESHOLD:
            print(f"[ANALYSIS] Gemini success for email_id={email_record.get('id')} category={validated.get('primary_category')} priority={validated.get('priority')}")
            return validated
        if validated:
            print(f"[ANALYSIS] Gemini low confidence for email_id={email_record.get('id')} confidence={validated['confidence']}")
    except Exception as exc:
        print(f"[ANALYSIS] Gemini failure for email_id={email_record.get('id')} message_id={email_record.get('gmail_message_id')} error={exc}")
        return None

    print(f"[ANALYSIS] Gemini returned invalid payload for email_id={email_record.get('id')} message_id={email_record.get('gmail_message_id')}")
    return None


def _apply_attention_policy(classification: dict[str, Any], email_text: str = "") -> dict[str, Any]:
    """Derive user impact from the chosen category and concrete message intent."""
    return _apply_semantic_attention_policy(classification, email_text)

    category = classification.get("category") or classification.get("primary_category") or "INFORMATION"
    category = _normalize_category(category)
    context = " ".join(
        filter(
            None,
            [
                email_text,
                str(classification.get("action_description") or ""),
                str(classification.get("reason") or ""),
            ],
        )
    )
    lowered = context.lower()
    explicit_action = _has_action_intent(context) or bool(
        re.search(r"\b(?:apply\s+now|register\s+for|rsvp|confirm\s+(?:your\s+)?attendance|review\s+and\s+respond)\b", lowered)
    )
    urgent_signal = _contains_any(
        lowered,
        ["urgent", "immediately", "today", "tomorrow", "expires", "expiring", "compromised", "unauthorized", "payment failed", "critical"],
    )
    real_deadline = bool(classification.get("deadline")) or _contains_any(
        lowered,
        ["due by", "deadline", "submit by", "no later than", "closing date", "final date", "expiration"],
    )
    severe_alert = _contains_any(
        lowered,
        ["security alert", "suspicious login", "account compromised", "unauthorized login", "payment failed", "service disruption", "critical"],
    )

    priority = "LOW"
    attention = False
    action_required = False

    if category == "Action Required":
        action_required = explicit_action or bool(classification.get("action_required"))
        attention = action_required
        priority = "HIGH" if urgent_signal else "MEDIUM" if action_required else "LOW"
    elif category == "Upcoming Deadlines":
        action_required = real_deadline and (explicit_action or bool(classification.get("action_required")))
        attention = real_deadline
        priority = "HIGH" if real_deadline and urgent_signal else "MEDIUM" if real_deadline else "LOW"
    elif category == "Events & Invitations":
        action_required = explicit_action or _contains_any(lowered, ["confirm your attendance", "registration required"])
        attention = action_required
        priority = "MEDIUM" if action_required else "LOW"
    elif category == "Awaiting Response":
        attention = True
        action_required = False
        priority = "HIGH" if urgent_signal else "MEDIUM"
    elif category == "Opportunities":
        action_required = explicit_action and _contains_any(lowered, ["apply", "submit", "confirm", "respond", "reply"])
        attention = action_required
        priority = "HIGH" if action_required and urgent_signal else "MEDIUM" if action_required or classification.get("opportunity_description") else "LOW"
    elif category == "Important Alerts":
        action_required = severe_alert or explicit_action
        attention = action_required
        priority = "HIGH" if severe_alert else "MEDIUM" if attention else "LOW"
    elif category == "Updates":
        action_required = explicit_action and not _is_marketing_or_newsletter(context)
        attention = action_required
        priority = "MEDIUM" if action_required else "LOW"
    else:
        action_required = explicit_action and category != "Other"
        attention = action_required
        priority = "MEDIUM" if action_required else "LOW"

    classification["category"] = category
    classification["primary_category"] = category
    classification["priority"] = priority
    classification["attention"] = attention
    classification["requires_attention"] = attention
    classification["action_required"] = action_required
    return classification


def _apply_semantic_attention_policy(classification: dict[str, Any], email_text: str = "") -> dict[str, Any]:
    category = _normalize_category(classification.get("category") or classification.get("primary_category"))
    context = " ".join(filter(None, [email_text, str(classification.get("reason") or ""), str(classification.get("action_description") or "")]))
    explicit_action = _has_action_intent(context) or bool(classification.get("action_required"))
    severe_alert = _has_consequential_alert_intent(context) or category == "ALERTS"
    urgent = _contains_any(context, ["urgent", "immediately", "today", "tomorrow", "expires", "expiring", "critical"])
    action_required = explicit_action if category in {"ACTION_REQUIRED", "OPPORTUNITIES", "EVENTS", "ALERTS"} else False
    attention = action_required or (category == "ALERTS" and severe_alert)
    priority = "URGENT" if severe_alert and urgent else "HIGH" if severe_alert or (action_required and urgent) else "MEDIUM" if attention or category == "OPPORTUNITIES" else "LOW"
    classification["category"] = category
    classification["primary_category"] = category
    classification["action_required"] = action_required
    classification["attention"] = attention
    classification["requires_attention"] = attention
    classification["priority"] = priority
    return classification


def validate_classification(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    category = _normalize_category(payload.get("category") or payload.get("primary_category"))
    if category not in APPROVED_CATEGORIES:
        return None

    confidence_value = payload.get("confidence", 0)
    try:
        confidence_float = float(confidence_value)
    except (TypeError, ValueError):
        confidence_float = 0.0
    if 0.0 <= confidence_float <= 1.0:
        confidence_float *= 100.0
    confidence_float = max(0.0, min(float(confidence_float), 100.0))

    action_required_value = payload.get("action_required")
    if action_required_value is None and payload.get("requires_attention") is not None:
        action_required_value = payload.get("requires_attention")

    attention_value = payload.get("attention")
    if attention_value is None:
        attention_value = payload.get("requires_attention")
    if attention_value is None:
        attention_value = payload.get("attention_flag")

    waiting_value = payload.get("waiting_for_response")
    if waiting_value is None:
        waiting_value = payload.get("awaiting_response")

    offer_description = payload.get("offer_description") or payload.get("opportunity_description") or ""
    reason = payload.get("reason") or "Classification based on email content and context."
    action_description = payload.get("action_description") or "Review this email for context."

    completed = {
        "category": category,
        "primary_category": category,
        "attention": _normalize_attention(attention_value),
        "requires_attention": bool(_safe_bool(payload.get("requires_attention", attention_value))),
        "priority": _normalize_priority(payload.get("priority")),
        "action_required": bool(_safe_bool(action_required_value)),
        "action_description": str(action_description).strip() or "Review this email for context.",
        "deadline": _coerce_datetime(payload.get("deadline")) if payload.get("deadline") else None,
        "event_date": _coerce_datetime(payload.get("event_date")) if payload.get("event_date") else None,
        "waiting_for_response": bool(_safe_bool(waiting_value)),
        "awaiting_response": bool(_safe_bool(waiting_value)),
        "offer_description": str(offer_description).strip(),
        "opportunity_description": str(offer_description).strip(),
        "reason": str(reason).strip() or "Classification based on email content and context.",
        "confidence": round(confidence_float, 2),
        "can_reply": bool(_safe_bool(payload.get("can_reply"))),
        "reply_reason": str(payload.get("reply_reason") or "").strip() or "No reply needed based on the email context.",
        "secondary_signals": payload.get("secondary_signals") if isinstance(payload.get("secondary_signals"), dict) else {},
    }

    if category == "INFORMATION":
        action_context = f"{completed['action_description']} {completed['reason']}".lower()
        if _has_action_intent(action_context):
            completed["category"] = "ACTION_REQUIRED"
            completed["primary_category"] = "ACTION_REQUIRED"
            completed["action_required"] = True
            completed["attention"] = True
            completed["requires_attention"] = True
            completed["priority"] = "HIGH"

    if completed["category"] not in APPROVED_CATEGORIES:
        return None

    return completed


def _get_email_record_by_message_id(user_id: str, gmail_message_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, user_id, gmail_message_id, gmail_thread_id, sender, sender_name, subject, received_at, gmail_url, snippet
                FROM emails
                WHERE user_id = :user_id
                  AND gmail_message_id = :gmail_message_id
                LIMIT 1
                """
            ),
            {"user_id": user_id, "gmail_message_id": gmail_message_id},
        ).fetchone()

    if not row:
        return None

    return {
        "id": str(row[0]),
        "user_id": str(row[1]),
        "gmail_message_id": row[2],
        "gmail_thread_id": row[3],
        "sender": row[4],
        "sender_name": row[5],
        "subject": row[6],
        "received_at": row[7],
        "gmail_url": row[8],
        "snippet": row[9],
    }


def _get_email_analysis_row(email_id: str) -> str | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id
                FROM email_analysis
                WHERE email_id = :email_id
                LIMIT 1
                """
            ),
            {"email_id": email_id},
        ).fetchone()

    return str(row[0]) if row else None


def _get_cached_analysis(email_id: str, content_hash: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT category,
                       primary_category,
                       attention,
                       requires_attention,
                       priority,
                       action_required,
                       action_description,
                       deadline,
                       event_date,
                       waiting_for_response,
                       awaiting_response,
                       offer_description,
                       opportunity_description,
                       reason,
                       confidence,
                       can_reply,
                       reply_reason,
                       secondary_signals,
                       content_hash,
                       classifier_version
                FROM email_analysis
                WHERE email_id = :email_id
                  AND content_hash = :content_hash
                  AND classifier_version = :classifier_version
                LIMIT 1
                """
            ),
            {
                "email_id": email_id,
                "content_hash": content_hash,
                "classifier_version": CLASSIFIER_VERSION,
            },
        ).fetchone()

    if not row:
        return None

    return {
        "category": row[0],
        "primary_category": row[1] or row[0],
        "attention": bool(row[2]),
        "requires_attention": bool(row[3]),
        "priority": row[4] or "LOW",
        "action_required": bool(row[5]),
        "action_description": row[6] or "Review this email for context.",
        "deadline": row[7].isoformat() if row[7] else None,
        "event_date": row[8].isoformat() if row[8] else None,
        "waiting_for_response": bool(row[9]),
        "awaiting_response": bool(row[10]),
        "offer_description": row[11] or "",
        "opportunity_description": row[12] or "",
        "reason": row[13] or "Classification based on the actual email content and intent.",
        "confidence": float(row[14]) if row[14] is not None else 0.0,
        "can_reply": bool(row[15]),
        "reply_reason": row[16] or "No reply needed based on the email context.",
        "secondary_signals": json.loads(row[17]) if isinstance(row[17], str) else row[17] or {},
    }


def _build_information_classification(reason: str = "The email is informational or lacks a stronger primary intent.") -> dict[str, Any]:
    return {
        "category": "INFORMATION",
        "primary_category": "INFORMATION",
        "attention": False,
        "requires_attention": False,
        "priority": "LOW",
        "action_required": False,
        "action_description": "No immediate action is required based on the available context.",
        "deadline": None,
        "event_date": None,
        "waiting_for_response": False,
        "awaiting_response": False,
        "offer_description": "",
        "opportunity_description": "",
        "reason": reason,
        "confidence": 0.0,
        "can_reply": False,
        "reply_reason": "No reply is required based on the available context.",
        "secondary_signals": {},
    }


def _persist_analysis(
    email_id: str,
    classification: dict[str, Any],
    content_hash: str,
    gemini_used: bool,
) -> dict[str, Any]:
    category = classification.get("category") or classification.get("primary_category") or "INFORMATION"
    attention_value = classification.get("attention")
    if attention_value is None:
        attention_value = classification.get("requires_attention")
    waiting_value = classification.get("waiting_for_response")
    if waiting_value is None:
        waiting_value = classification.get("awaiting_response")
    offer_value = classification.get("offer_description") or classification.get("opportunity_description") or ""

    record = {
        "email_id": email_id,
        "category": category,
        "primary_category": category,
        "attention": bool(attention_value),
        "requires_attention": bool(classification.get("requires_attention", attention_value)),
        "priority": classification.get("priority") or "MEDIUM",
        "action_required": bool(classification.get("action_required")),
        "action_description": classification.get("action_description") or "Review this email for context.",
        "deadline": classification.get("deadline"),
        "event_date": classification.get("event_date"),
        "waiting_for_response": bool(waiting_value),
        "awaiting_response": bool(waiting_value),
        "offer_description": offer_value,
        "opportunity_description": offer_value,
        "reason": classification.get("reason") or "Classification based on email content and context.",
        "confidence": classification.get("confidence") or 0.0,
        "can_reply": bool(classification.get("can_reply")),
        "reply_reason": classification.get("reply_reason") or "No reply needed based on the email context.",
        "content_hash": content_hash,
        "classifier_version": CLASSIFIER_VERSION,
        "gemini_used": gemini_used,
        "secondary_signals": json.dumps(classification.get("secondary_signals") or {}),
    }

    analysis_id = _get_email_analysis_row(email_id)

    with engine.begin() as connection:
        if analysis_id:
            connection.execute(
                text(
                    """
                    UPDATE email_analysis
                    SET category = :category,
                        primary_category = :primary_category,
                        attention = :attention,
                        requires_attention = :requires_attention,
                        priority = :priority,
                        action_required = :action_required,
                        action_description = :action_description,
                        deadline = :deadline,
                        event_date = :event_date,
                        waiting_for_response = :waiting_for_response,
                        awaiting_response = :awaiting_response,
                        offer_description = :offer_description,
                        opportunity_description = :opportunity_description,
                        reason = :reason,
                        confidence = :confidence,
                        can_reply = :can_reply,
                        reply_reason = :reply_reason,
                        content_hash = :content_hash,
                        classifier_version = :classifier_version,
                        gemini_used = :gemini_used,
                        secondary_signals = :secondary_signals,
                        updated_at = NOW()
                    WHERE id = :analysis_id
                    """
                ),
                {"analysis_id": analysis_id, **record},
            )
        else:
            connection.execute(
                text(
                    """
                    INSERT INTO email_analysis (
                        email_id,
                        category,
                        primary_category,
                        attention,
                        requires_attention,
                        priority,
                        action_required,
                        action_description,
                        deadline,
                        event_date,
                        waiting_for_response,
                        awaiting_response,
                        offer_description,
                        opportunity_description,
                        reason,
                        confidence,
                        can_reply,
                        reply_reason,
                        content_hash,
                        classifier_version,
                        gemini_used
                        , secondary_signals
                    )
                    VALUES (
                        :email_id,
                        :category,
                        :primary_category,
                        :attention,
                        :requires_attention,
                        :priority,
                        :action_required,
                        :action_description,
                        :deadline,
                        :event_date,
                        :waiting_for_response,
                        :awaiting_response,
                        :offer_description,
                        :opportunity_description,
                        :reason,
                        :confidence,
                        :can_reply,
                        :reply_reason,
                        :content_hash,
                        :classifier_version,
                        :gemini_used
                        , :secondary_signals
                    )
                    ON CONFLICT (email_id) DO UPDATE SET
                        category = EXCLUDED.category,
                        primary_category = EXCLUDED.primary_category,
                        attention = EXCLUDED.attention,
                        requires_attention = EXCLUDED.requires_attention,
                        priority = EXCLUDED.priority,
                        action_required = EXCLUDED.action_required,
                        action_description = EXCLUDED.action_description,
                        deadline = EXCLUDED.deadline,
                        event_date = EXCLUDED.event_date,
                        waiting_for_response = EXCLUDED.waiting_for_response,
                        awaiting_response = EXCLUDED.awaiting_response,
                        offer_description = EXCLUDED.offer_description,
                        opportunity_description = EXCLUDED.opportunity_description,
                        reason = EXCLUDED.reason,
                        confidence = EXCLUDED.confidence,
                        can_reply = EXCLUDED.can_reply,
                        reply_reason = EXCLUDED.reply_reason,
                        content_hash = EXCLUDED.content_hash,
                        classifier_version = EXCLUDED.classifier_version,
                        gemini_used = EXCLUDED.gemini_used,
                        secondary_signals = EXCLUDED.secondary_signals,
                        updated_at = NOW()
                    """
                ),
                record,
            )

    return classification


def analyze_email_for_user(
    user_id: str,
    gmail_message_id: str,
    force_reclassify: bool = False,
) -> dict[str, Any]:
    email_record = _get_email_record_by_message_id(user_id, gmail_message_id)
    if not email_record:
        raise ValueError("Email not found for this user")

    from backend.app import main as app_main

    print(f"[ANALYSIS] starting email_id={email_record['id']} message_id={gmail_message_id}")

    analysis_started_at = time.perf_counter()
    access_token, refresh_token, _ = app_main._get_user_oauth_record(user_id)
    access_token = app_main._ensure_fresh_google_access_token(user_id, access_token, refresh_token)
    credentials = app_main.Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=app_main.GOOGLE_CLIENT_ID,
        client_secret=app_main.GOOGLE_CLIENT_SECRET,
    )
    gmail_service = app_main.build("gmail", "v1", credentials=credentials)

    gmail_fetch_started_at = time.perf_counter()
    message = gmail_service.users().messages().get(
        userId="me",
        id=gmail_message_id,
        format="full",
    ).execute()
    gmail_fetch_seconds = time.perf_counter() - gmail_fetch_started_at

    parse_started_at = time.perf_counter()
    raw_email_text = _extract_email_text(message)
    normalized_email = normalize_email_message(message, email_record)
    email_text = normalized_email.get("cleaned_text") or raw_email_text
    content_hash = _email_content_hash(email_record, email_text)
    parse_seconds = time.perf_counter() - parse_started_at

    if not force_reclassify:
        cached = _get_cached_analysis(email_record["id"], content_hash)
        if cached:
            print(f"[ANALYSIS] cache hit email_id={email_record['id']} message_id={gmail_message_id} classifier={CLASSIFIER_VERSION}")
            return {
                "gmail_message_id": gmail_message_id,
                "analysis": cached,
            }

    categorize_started_at = time.perf_counter()
    signals = extract_local_signals(normalized_email)
    deterministic = _build_semantic_signals(email_record, email_text)
    gemini_required = should_use_gemini(signals, email_text, deterministic)
    gemini_result = _call_gemini_for_classification(email_record, email_text, signals) if gemini_required else None
    gemini_called = gemini_required
    final = gemini_result if gemini_result else deterministic

    final = validate_classification(final) or _build_information_classification()
    final = _apply_semantic_attention_policy(final, email_text)
    categorize_seconds = time.perf_counter() - categorize_started_at

    persist_started_at = time.perf_counter()
    _persist_analysis(email_record["id"], final, content_hash, gemini_called)
    persist_seconds = time.perf_counter() - persist_started_at
    print(
        f"[ANALYSIS] email_id={email_record['id']} message_id={gmail_message_id} "
        f"primary_category={final['primary_category']} requires_attention={final['requires_attention']} "
        f"priority={final['priority']} gemini_called={gemini_called}"
    )
    print(
        f"[ANALYSIS_TIMING] message_id={gmail_message_id} "
        f"gmail_fetch_seconds={gmail_fetch_seconds:.3f} parse_seconds={parse_seconds:.3f} "
        f"categorize_seconds={categorize_seconds:.3f} persist_seconds={persist_seconds:.3f} "
        f"total_seconds={time.perf_counter() - analysis_started_at:.3f}"
    )
    return {
        "gmail_message_id": gmail_message_id,
        "analysis": final,
    }


def analyze_user_emails_batch(
    user_id: str,
    gmail_message_ids: list[str] | None = None,
    force_reclassify: bool = False,
) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        if gmail_message_ids:
            rows = connection.execute(
                text(
                    """
                    SELECT gmail_message_id
                    FROM emails
                    WHERE user_id = :user_id
                      AND gmail_message_id = ANY(:gmail_message_ids)
                    ORDER BY received_at DESC NULLS LAST, created_at DESC
                    """
                ),
                {"user_id": user_id, "gmail_message_ids": gmail_message_ids},
            ).fetchall()
        else:
            rows = connection.execute(
                text(
                    """
                    SELECT gmail_message_id
                    FROM emails
                    WHERE user_id = :user_id
                    ORDER BY received_at DESC NULLS LAST, created_at DESC
                    LIMIT 30
                    """
                ),
                {"user_id": user_id},
            ).fetchall()

    message_ids = [row[0] for row in rows]
    results = []
    for message_id in message_ids:
        try:
            results.append(analyze_email_for_user(user_id, message_id, force_reclassify=force_reclassify))
        except Exception:
            continue
    return results


def reclassify_existing_emails(user_id: str, use_gemini: bool = True) -> dict[str, Any]:
    """Reclassify persisted messages without downloading them from Gmail again."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT e.id, e.gmail_message_id, e.sender, e.sender_name, e.subject, e.snippet,
                       a.deadline, a.event_date, a.action_description, a.action_required,
                       a.waiting_for_response, a.awaiting_response, a.offer_description,
                       a.opportunity_description
                FROM emails e
                LEFT JOIN email_analysis a ON a.email_id = e.id
                WHERE e.user_id = :user_id
                ORDER BY e.received_at DESC NULLS LAST, e.created_at DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()

    counts: dict[str, int] = {}
    gemini_count = 0
    for row in rows:
        email_record = dict(row)
        text_value = "\n".join(
            filter(None, [email_record.get("subject"), email_record.get("sender_name"), email_record.get("sender"), email_record.get("snippet")])
        )
        classification = _build_semantic_signals(email_record, text_value)
        local_signals = extract_local_signals(
            {"subject": email_record.get("subject") or "", "sender": email_record.get("sender") or "", "cleaned_text": text_value}
        )
        if use_gemini and should_use_gemini(local_signals, text_value, classification):
            gemini_result = _call_gemini_for_classification(email_record, text_value, local_signals)
            if gemini_result:
                classification = gemini_result
                gemini_count += 1

        if not classification.get("deadline") and email_record.get("deadline"):
            classification["deadline"] = email_record["deadline"].isoformat()
        if not classification.get("event_date") and email_record.get("event_date"):
            classification["event_date"] = email_record["event_date"].isoformat()
        if not classification.get("action_description") and email_record.get("action_description"):
            classification["action_description"] = email_record["action_description"]
        classification = validate_classification(classification) or _build_information_classification()
        classification = _apply_semantic_attention_policy(classification, text_value)
        _persist_analysis(
            str(email_record["id"]),
            classification,
            _email_content_hash(email_record, text_value),
            bool(use_gemini and classification.get("confidence", 0) >= GEMINI_CONFIDENCE_THRESHOLD),
        )
        category = classification["primary_category"]
        counts[category] = counts.get(category, 0) + 1

    return {"reclassified": len(rows), "gemini_used": gemini_count, "by_category": counts}


def list_user_emails_with_analysis(user_id: str, category: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT e.id,
                       e.gmail_message_id,
                       e.gmail_thread_id,
                       e.sender,
                       e.sender_name,
                       e.subject,
                       e.received_at,
                       e.gmail_url,
                       e.snippet,
                       COALESCE(a.category, a.primary_category) AS category,
                       COALESCE(a.attention, a.requires_attention) AS attention,
                       a.requires_attention,
                       a.priority,
                       a.action_required,
                       a.action_description,
                       a.deadline,
                       a.event_date,
                       COALESCE(a.waiting_for_response, a.awaiting_response) AS waiting_for_response,
                       a.awaiting_response,
                       COALESCE(a.offer_description, a.opportunity_description) AS offer_description,
                       a.opportunity_description,
                       a.reason,
                       a.confidence,
                       a.can_reply,
                       a.reply_reason,
                       e.created_at,
                       e.updated_at
                FROM emails e
                LEFT JOIN email_analysis a ON a.email_id = e.id
                WHERE e.user_id = :user_id
                  AND (:category IS NULL OR COALESCE(a.category, a.primary_category) = :category)
                ORDER BY e.received_at DESC NULLS LAST, e.created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "category": category, "limit": limit},
        ).fetchall()

    payload = []
    for row in rows:
        analysis = None
        if row[9] is not None:
            analysis = {
                "category": row[9],
                "primary_category": row[9],
                "attention": row[10],
                "requires_attention": row[11],
                "priority": row[12],
                "action_required": row[13],
                "action_description": row[14],
                "deadline": row[15].isoformat() if row[15] else None,
                "event_date": row[16].isoformat() if row[16] else None,
                "waiting_for_response": row[17],
                "awaiting_response": row[18],
                "offer_description": row[19],
                "opportunity_description": row[20],
                "reason": row[21],
                "confidence": float(row[22]) if row[22] is not None else None,
                "can_reply": row[23],
                "reply_reason": row[24],
            }

        payload.append(
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
                "analysis": analysis,
                "created_at": row[25].isoformat() if row[25] else None,
                "updated_at": row[26].isoformat() if row[26] else None,
            }
        )

    return payload


def get_attention_summary(user_id: str) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT COALESCE(a.primary_category, a.category) AS category,
                       COUNT(*) AS total,
                       SUM(CASE WHEN a.requires_attention THEN 1 ELSE 0 END) AS requires_attention
                FROM emails e
                LEFT JOIN email_analysis a ON a.email_id = e.id
                WHERE e.user_id = :user_id
                GROUP BY COALESCE(a.primary_category, a.category)
                ORDER BY total DESC
                """
            ),
            {"user_id": user_id},
        ).fetchall()

    categories = {row[0]: {"count": row[1], "requires_attention": row[2]} for row in rows if row[0]}
    return {
        "total_emails": sum(item["count"] for item in categories.values()),
        "requires_attention": sum(item["requires_attention"] for item in categories.values()),
        "by_category": categories,
    }

import re
from typing import Any


KEYWORD_GROUPS = {
    "job": [
        "hiring", "recruitment", "job opening", "job opportunity", "position available",
        "vacancy", "internship", "intern", "we are hiring", "apply now", "career", "career opportunity", "recruiter", "scholarship", "opening",
        "software engineer", "full stack developer", "app developer", "selected", "shortlisted"
    ],
    "reply_request": [
        "please reply", "please respond", "kindly reply", "kindly confirm", "let me know",
        "confirm", "confirm your", "reply to", "respond by", "please share", "provide", "send us"
    ],
    "confirmation_request": [
        "please confirm", "confirm your availability", "confirm attendance", "rsvp",
        "confirm receipt", "confirmation required", "let us know if you can", "accept or decline"
    ],
    "submission_request": [
        "submit", "upload", "complete", "share the", "attach", "fill out", "finalize"
    ],
    "registration_request": [
        "register", "registration", "sign up", "reserve your seat", "join us", "attend"
    ],
    "deadline": [
        "deadline", "due by", "submit by", "expires", "expiration", "closing date", "final date",
        "no later than", "before", "application deadline", "application closes", "registration closes", "valid until", "last date"
    ],
    "event": [
        "meeting", "interview", "appointment", "webinar", "conference", "workshop", "seminar", "meetup", "event", "invitation", "invited",
        "calendar invite", "calendar invitation", "scheduled for", "session for", "assessment"
    ],
    "security_alert": [
        "security alert", "suspicious login", "suspicious activity", "password changed", "account compromised", "account locked",
        "unauthorized login", "verification code", "two factor", "2fa", "security update"
    ],
    "financial_alert": [
        "payment failed", "payment failure", "billing issue", "fraud alert", "transaction", "debit", "credit", "banking", "credit card", "bank alert"
    ],
    "account_alert": [
        "account changes", "account warning", "account locked", "important account notification", "critical account notification", "account update", "login from a new device", "service disruption"
    ],
    "newsletter": [
        "newsletter", "weekly update", "monthly update", "company update", "product update", "status update"
    ],
    "promotional": [
        "sale", "promo", "flash sale", "limited time", "special offer", "discount", "marketing",
        "unsubscribe", "last chance savings", "course sale"
    ],
    "awaiting_response": [
        "awaiting your response", "waiting for your response", "response pending", "pending response", "we will get back to you", "we will contact you shortly", "we'll contact you", "under review", "we are reviewing",
        "reviewing your application", "your application is under review", "we will follow up"
    ],
}


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    normalized = _normalize_text(text)
    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        pattern = re.escape(normalized_keyword).replace(r"\ ", r"\s+")
        if re.search(rf"\b{pattern}\b", normalized):
            return True
    return False


def _extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            value = match.group(0).strip()
            if value not in matches:
                matches.append(value)
    return matches


def extract_local_signals(normalized_email: dict[str, Any]) -> dict[str, Any]:
    text = normalized_email.get("cleaned_text") or normalized_email.get("raw_text") or ""
    subject = normalized_email.get("subject") or ""
    sender = normalized_email.get("sender") or ""
    full_text = " ".join(value for value in [subject, sender, text] if value)

    signals: dict[str, Any] = {
        "has_job_signal": _contains_any(full_text, KEYWORD_GROUPS["job"]),
        "has_recruitment_signal": _contains_any(full_text, ["recruitment", "we are hiring", "hiring", "job opening"]),
        "has_internship_signal": _contains_any(full_text, ["internship", "summer internship", "graduate internship"]),
        "has_application_signal": _contains_any(full_text, ["application", "applied", "apply now", "your application"]),
        "has_interview_signal": _contains_any(full_text, ["interview", "technical interview", "screening call"]),
        "has_meeting_signal": _contains_any(full_text, ["meeting", "team meeting", "call with"]),
        "has_event_signal": _contains_any(full_text, KEYWORD_GROUPS["event"]),
        "has_invitation_signal": _contains_any(full_text, ["invitation", "calendar invite", "invite"]),
        "has_deadline_signal": _contains_any(full_text, KEYWORD_GROUPS["deadline"]),
        "has_reply_request": _contains_any(full_text, KEYWORD_GROUPS["reply_request"]),
        "has_confirmation_request": _contains_any(full_text, KEYWORD_GROUPS["confirmation_request"]),
        "has_submission_request": _contains_any(full_text, KEYWORD_GROUPS["submission_request"]),
        "has_registration_request": _contains_any(full_text, KEYWORD_GROUPS["registration_request"]),
        "has_security_alert": _contains_any(full_text, KEYWORD_GROUPS["security_alert"]),
        "has_financial_alert": _contains_any(full_text, KEYWORD_GROUPS["financial_alert"]),
        "has_account_alert": _contains_any(full_text, KEYWORD_GROUPS["account_alert"]),
        "has_newsletter_signal": _contains_any(full_text, KEYWORD_GROUPS["newsletter"]),
        "has_promotional_signal": _contains_any(full_text, KEYWORD_GROUPS["promotional"]),
        "has_awaiting_response_signal": _contains_any(full_text, KEYWORD_GROUPS["awaiting_response"]),
        "detected_dates": _extract_dates(full_text),
        "detected_deadlines": _extract_dates(full_text) if _contains_any(full_text, KEYWORD_GROUPS["deadline"]) else [],
        "action_phrases": [
            phrase for phrase in [
                "please reply", "please respond", "let me know", "confirm", "submit", "register", "apply now",
                "provide", "verify", "rsvp", "complete"
            ] if phrase in _normalize_text(full_text)
        ],
        "event_phrases": [
            phrase for phrase in ["interview", "meeting", "webinar", "appointment", "event", "invitation"]
            if phrase in _normalize_text(full_text)
        ],
        "important_entities": sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+)*\b", subject + " " + text)))[:12],
    }

    return signals

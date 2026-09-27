import html as html_lib
import re
from typing import Any


def _decode_gmail_data(data: str | None) -> str:
    if not data:
        return ""
    try:
        import base64

        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _decode_gmail_part(part: dict[str, Any]) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    try:
        import base64

        padded = data + "=" * (-len(data) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return ""

    content_type = next(
        (str(header.get("value") or "") for header in part.get("headers", []) if str(header.get("name") or "").lower() == "content-type"),
        "",
    )
    charset_match = re.search(r"charset\s*=\s*[\"']?([^;\"']+)", content_type, flags=re.I)
    charset = charset_match.group(1).strip() if charset_match else "utf-8"
    try:
        return decoded.decode(charset, errors="replace")
    except LookupError:
        return decoded.decode("utf-8", errors="replace")


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""

    cleaned = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.I | re.S)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?:\b(?:unsubscribe|unsubscribe here|view in browser|manage preferences|privacy policy|terms of service|opt out|update your preferences)\b.*?)+", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?i)\b(?:image|pixel|tracking|newsletter|marketing|offer|sale)\b.*?", " ", cleaned)
    return cleaned.strip()


def _clean_email_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[\t ]+", " ", cleaned)
    cleaned = re.sub(r"\n +", "\n", cleaned)
    cleaned = re.sub(r"(?m)^\s*(?:--|___|thank you|thanks|best regards|regards|sincerely|unsubscribe|view in browser|manage preferences|privacy policy)\s*$", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_body_from_message(message: dict[str, Any]) -> str:
    payload = message.get("payload") or {}
    parts = payload.get("parts") or []
    text_chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime_type = str(part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime_type.startswith("text/"):
            decoded = _decode_gmail_data(data)
            if decoded:
                text_chunks.append(decoded)
        if part.get("parts"):
            for child in part["parts"]:
                walk(child)
        if mime_type == "text/html" and data:
            decoded = _decode_gmail_data(data)
            if decoded:
                text_chunks.append(_strip_html(decoded))

    for part in parts:
        walk(part)

    if not text_chunks:
        body = payload.get("body") or {}
        data = body.get("data")
        if data:
            html_text = _decode_gmail_data(data)
            if html_text:
                text_chunks.append(_strip_html(html_text) if "<" in html_text else html_text)

    if not text_chunks:
        body = payload.get("body") or {}
        body_text = body.get("data")
        if body_text:
            text_chunks.append(_decode_gmail_data(body_text))

    combined = "\n".join(text_chunks)
    if "<" in combined and "</" in combined:
        combined = _strip_html(combined)
    return _clean_email_text(combined)


def _extract_original_bodies(message: dict[str, Any]) -> tuple[str, str]:
    payload = message.get("payload") or {}
    html_chunks: list[str] = []
    text_chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime_type = str(part.get("mimeType") or "").lower()
        data = (part.get("body") or {}).get("data")
        if data and mime_type == "text/html":
            html_chunks.append(_decode_gmail_part(part))
        elif data and mime_type == "text/plain":
            text_chunks.append(_decode_gmail_part(part))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    if not html_chunks and not text_chunks:
        decoded = _decode_gmail_part(payload)
        if decoded:
            if str(payload.get("mimeType") or "").lower() == "text/html":
                html_chunks.append(decoded)
            else:
                text_chunks.append(decoded)

    return (text_chunks[0] if text_chunks else "", html_chunks[0] if html_chunks else "")


def normalize_email_message(message: dict[str, Any], email_record: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    header_map = {str(h.get("name") or "").lower(): str(h.get("value") or "") for h in headers if h.get("name")}

    sender = header_map.get("from") or email_record.get("sender") if email_record else ""
    if sender and "<" in sender and ">" in sender:
        sender = sender.split("<")[-1].split(">", 1)[0].strip()

    sender_name = ""
    if header_map.get("from"):
        raw_from = header_map["from"]
        if "<" in raw_from and ">" in raw_from:
            sender_name = raw_from.split("<", 1)[0].strip().strip('"')
        elif raw_from:
            sender_name = raw_from.strip().strip('"')
    if not sender_name and email_record:
        sender_name = str(email_record.get("sender_name") or "").strip()

    subject = header_map.get("subject") or (email_record.get("subject") if email_record else "") or ""
    snippet = str(message.get("snippet") or (email_record.get("snippet") if email_record else "") or "").strip()
    received_at = message.get("internalDate")
    gmail_message_id = str(message.get("id") or (email_record.get("gmail_message_id") if email_record else "") or "")
    gmail_thread_id = str(message.get("threadId") or (email_record.get("gmail_thread_id") if email_record else "") or "")

    body_text = _extract_body_from_message(message)
    original_text, original_html = _extract_original_bodies(message)
    cleaned_body = _clean_email_text(body_text)
    combined_text = " ".join(part for part in [subject, sender_name, sender, snippet, cleaned_body] if part).strip()

    return {
        "sender": sender,
        "sender_name": sender_name,
        "subject": subject,
        "received_at": received_at,
        "snippet": snippet,
        "gmail_message_id": gmail_message_id,
        "gmail_thread_id": gmail_thread_id,
        "body_text": cleaned_body,
        "original_body": original_text,
        "html_body": original_html,
        "cleaned_text": combined_text,
        "raw_text": combined_text,
    }

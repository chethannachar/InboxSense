import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine
print("DB_OK")
with engine.connect() as conn:
    print("EMAILS_COUNT", conn.execute(text("SELECT COUNT(*) FROM emails")).scalar())
    print("ANALYSIS_COUNT", conn.execute(text("SELECT COUNT(*) FROM email_analysis")).scalar())
    print("EMAIL_ROWS")
    for r in conn.execute(text("SELECT id, gmail_message_id, sender, subject, snippet, received_at FROM emails ORDER BY received_at DESC NULLS LAST, created_at DESC LIMIT 10")).fetchall():
        print(r)
    print("ANALYSIS_ROWS")
    for r in conn.execute(text("SELECT email_id, primary_category, priority, requires_attention, action_required, action_description, reason, confidence FROM email_analysis ORDER BY analyzed_at DESC LIMIT 10")).fetchall():
        print(r)

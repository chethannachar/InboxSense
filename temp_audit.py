from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = "postgresql+psycopg2://" + quote_plus("postgres") + ":" + quote_plus("chethanachar03") + "@localhost:5432/Email"
engine = create_engine(url)
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

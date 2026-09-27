import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

from backend.app import main as backend_main

url = "postgresql+psycopg2://" + quote_plus("postgres") + ":" + quote_plus("chethanachar03") + "@localhost:5432/Email"
engine = create_engine(url)

print("DB_OK")
with engine.connect() as conn:
    print("USERS")
    for row in conn.execute(text("SELECT id, email FROM users ORDER BY created_at")).fetchall():
        print(row)
    print("EMAILS_BY_USER")
    for row in conn.execute(text("SELECT user_id, COUNT(*) FROM emails GROUP BY user_id ORDER BY COUNT(*) DESC")).fetchall():
        print(row)
    user = conn.execute(text("SELECT id, email FROM users WHERE email = :email LIMIT 1"), {"email": "chethannagesh06@gmail.com"}).fetchone()
    print("USER", user)
    message_id = "1a0d318e26650a2c"
    email_row = conn.execute(text("SELECT id, gmail_message_id, sender, sender_name, subject, received_at, gmail_url, snippet FROM emails WHERE gmail_message_id = :mid"), {"mid": message_id}).fetchone()
    print("EMAIL_ROW", email_row)
    if email_row:
        row = conn.execute(text("SELECT email_id, primary_category, priority, requires_attention, action_required, action_description, reason, confidence FROM email_analysis WHERE email_id = :eid"), {"eid": email_row[0]}).fetchone()
        print("ANALYSIS_ROW", row)

client = TestClient(backend_main.app)
user_id = str(user[0])
encoded_cookie = backend_main._build_session_cookie_value(user_id)
response = client.get("/api/emails?limit=30&include_analysis=true", cookies={"session_user_id": encoded_cookie})
print("STATUS", response.status_code)
items = response.json()
print("ITEM_COUNT", len(items))
for item in items:
    if item.get("gmail_message_id") == message_id:
        print("API_ITEM", json.dumps(item, indent=2, default=str))
        break

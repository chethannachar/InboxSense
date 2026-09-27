import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def build_database_url(
	host: str | None = None,
	port: str | None = None,
	database: str | None = None,
	username: str | None = None,
	password: str | None = None,
) -> str:
	host = host or os.getenv("DB_HOST", "localhost")
	port = port or os.getenv("DB_PORT", "5432")
	database = database or os.getenv("DB_NAME", "gmail_attention")
	username = username or os.getenv("DB_USER", "postgres")
	password = password if password is not None else os.getenv("DB_PASSWORD", "")

	return (
		"postgresql+psycopg2://"
		f"{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}"
	)


DATABASE_URL = os.getenv("DATABASE_URL") or build_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

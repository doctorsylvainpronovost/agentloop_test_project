import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/weather"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def is_postgresql_url(url: str) -> bool:
    normalized = url.lower()
    return normalized.startswith("postgresql://") or normalized.startswith("postgresql+")

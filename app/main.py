from fastapi import FastAPI

from app.config import get_database_url

app = FastAPI(title="Weather API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database_url": get_database_url()}

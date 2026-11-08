"""Application configuration and filesystem paths.

Paths are resolved relative to the backend package so the API works no matter
which directory uvicorn/pytest is launched from.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BACKEND_DIR / "storage"))).resolve()
DATASETS_DIR = STORAGE_DIR / "datasets"
MODELS_DIR = STORAGE_DIR / "models"
EXPORTS_DIR = STORAGE_DIR / "exports"

for directory in (STORAGE_DIR, DATASETS_DIR, MODELS_DIR, EXPORTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DEFAULT_DATABASE_URL = "sqlite:///" + str(BACKEND_DIR / "datalab.db").replace("\\", "/")
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

SECRET_KEY = os.getenv("SECRET_KEY", "data-lab-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
ALLOWED_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

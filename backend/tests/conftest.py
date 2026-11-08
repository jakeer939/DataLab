"""Shared pytest fixtures for the DataLab backend.

The test suite runs against a throw-away SQLite database and storage directory
so it can never touch the developer's real ``datalab.db`` or uploaded files.
Environment variables are set *before* importing the application because the
configuration module resolves them at import time.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="datalab_tests_"))
TEST_DB_PATH = TEST_ROOT / "test.db"
TEST_STORAGE = TEST_ROOT / "storage"

os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_DB_PATH).replace("\\", "/")
os.environ["STORAGE_DIR"] = str(TEST_STORAGE)
os.environ["SECRET_KEY"] = "datalab-test-secret"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


def register_user(client: TestClient, prefix: str = "user") -> dict:
    """Register a unique user and return headers plus the API payload."""
    suffix = uuid.uuid4().hex[:12]
    username = f"{prefix}_{suffix}"
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "Sup3rSecret!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "token": body["access_token"],
        "user": body["user"],
        "credentials": payload,
    }


@pytest.fixture
def user(client):
    return register_user(client, "owner")


@pytest.fixture
def other_user(client):
    return register_user(client, "other")


@pytest.fixture
def auth(user):
    return user["headers"]


@pytest.fixture
def other_auth(other_user):
    return other_user["headers"]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def classification_csv(rows: int = 60) -> bytes:
    """A small, deterministic classification dataset."""
    lines = ["id,name,age,score,category,target,event_date"]
    for index in range(rows):
        age = 20 + (index % 40)
        score = 40 + ((index * 7) % 55)
        category = ["alpha", "beta", "gamma"][index % 3]
        target = 1 if score >= 70 else 0
        lines.append(
            f"{index + 1},person_{index},{age},{score},{category},{target},2024-01-{(index % 28) + 1:02d}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def regression_csv(rows: int = 60) -> bytes:
    """A small, deterministic regression dataset."""
    lines = ["id,name,age,score,category,price"]
    for index in range(rows):
        age = 20 + (index % 40)
        score = 40 + ((index * 7) % 55)
        category = ["alpha", "beta", "gamma"][index % 3]
        price = 100 + 3.5 * age + 1.25 * score + (index % 5)
        lines.append(f"{index + 1},person_{index},{age},{score},{category},{price}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def messy_csv() -> bytes:
    """CSV with missing values, duplicates and an outlier."""
    rows = [
        "id,name,age,score,category",
        "1,Alice,25,88.5,A",
        "2,Bob,,72.0,B",
        "3,Cara,31,,A",
        "3,Cara,31,,A",
        "4,Dan,45,500.0,B",
        "5,Eve,29,65.0,C",
        "6,Frank,38,79.0,A",
        "7,Gina,22,91.0,B",
        "8,Hank,50,60.0,C",
        "9,Ivy,27,84.0,A",
        "10,Jack,33,70.0,B",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def upload_csv(
    client: TestClient,
    headers: dict,
    content: bytes,
    filename: str = "data.csv",
    name: str = "",
    mime: str = "text/csv",
):
    return client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": (filename, content, mime)},
        data={"name": name},
    )


@pytest.fixture
def uploaded_dataset(client, auth):
    response = upload_csv(client, auth, classification_csv(), name="Classification")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def uploaded_regression(client, auth):
    response = upload_csv(client, auth, regression_csv(), name="Regression")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

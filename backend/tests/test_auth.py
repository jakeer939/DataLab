from __future__ import annotations

import uuid

from app.database import SessionLocal
from app.models import Users
from app.security import hash_password


def unique_payload(prefix: str = "auth") -> dict:
    suffix = uuid.uuid4().hex[:10]
    return {
        "username": f"{prefix}_{suffix}",
        "email": f"{prefix}_{suffix}@example.com",
        "password": "Sup3rSecret!",
    }


def test_register_returns_token_and_user(client):
    payload = unique_payload()
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == payload["username"]
    assert body["user"]["email"] == payload["email"]
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_register_duplicate_username_conflicts(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    duplicate = {**payload, "email": f"other_{uuid.uuid4().hex[:8]}@example.com"}
    response = client.post("/api/v1/auth/register", json=duplicate)
    assert response.status_code == 409


def test_register_duplicate_email_conflicts(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    duplicate = {**payload, "username": f"other_{uuid.uuid4().hex[:8]}"}
    response = client.post("/api/v1/auth/register", json=duplicate)
    assert response.status_code == 409


def test_register_validation_errors(client):
    short_password = {**unique_payload(), "password": "123"}
    assert client.post("/api/v1/auth/register", json=short_password).status_code == 422

    bad_email = {**unique_payload(), "email": "not-an-email"}
    assert client.post("/api/v1/auth/register", json=bad_email).status_code == 422

    whitespace = {**unique_payload(), "username": "bad user"}
    assert client.post("/api/v1/auth/register", json=whitespace).status_code == 422


def test_login_by_username_and_email(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    by_username = client.post(
        "/api/v1/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    assert by_username.status_code == 200
    assert by_username.json()["access_token"]

    by_email = client.post(
        "/api/v1/auth/login",
        json={"username": payload["email"], "password": payload["password"]},
    )
    assert by_email.status_code == 200
    assert by_email.json()["access_token"]


def test_login_rejects_bad_credentials(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"username": payload["username"], "password": "WrongPassword!"},
    )
    assert wrong_password.status_code == 401

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"username": "does_not_exist", "password": "whatever"},
    )
    assert unknown_user.status_code == 401


def test_login_rejects_inactive_user(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    session = SessionLocal()
    try:
        user = session.query(Users).filter(Users.username == payload["username"]).one()
        user.is_active = False
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/api/v1/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    assert response.status_code == 403


def test_me_requires_authentication(client, auth):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


def test_me_rejects_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_me_accepts_legacy_query_token(client, user):
    response = client.get(f"/api/v1/auth/me?token={user['token']}")
    assert response.status_code == 200
    assert response.json()["username"] == user["user"]["username"]


def test_logout_is_stateless_acknowledgement(client, auth):
    response = client.post("/api/v1/auth/logout", headers=auth)
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_passwords_are_hashed_not_stored_plaintext(client):
    payload = unique_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    session = SessionLocal()
    try:
        user = session.query(Users).filter(Users.username == payload["username"]).one()
        assert user.password_hash != payload["password"]
        assert user.password_hash.startswith("$argon2")
    finally:
        session.close()


def test_hash_password_is_salted():
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second

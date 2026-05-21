"""Backend tests for Health Portal: Auth (register/login/me/logout) + Translate."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://health-portal-177.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

TEST_USERS = [
    {"name": "Test Doctor", "email": "doctor@test.com", "password": "Doctor123!", "user_type": "Doctor"},
    {"name": "Test Patient", "email": "patient@test.com", "password": "Patient123!", "user_type": "Patient"},
    {"name": "Test Pharmacist", "email": "pharmacist@test.com", "password": "Pharmacy123!", "user_type": "Pharmacist"},
    {"name": "Test Engineer", "email": "engineer@test.com", "password": "Engineer123!", "user_type": "Biomedical Engineer"},
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("message") == "Health Portal API"


@pytest.mark.parametrize("user", TEST_USERS)
def test_register_or_already_exists(session, user):
    r = session.post(f"{API}/auth/register", json=user)
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        data = r.json()
        assert "token" in data and "user" in data
        assert data["user"]["email"] == user["email"]
        assert data["user"]["user_type"] == user["user_type"]
        assert "password" not in data["user"]


def test_register_duplicate(session):
    r = session.post(f"{API}/auth/register", json=TEST_USERS[0])
    assert r.status_code == 400


def test_register_invalid_email(session):
    r = session.post(f"{API}/auth/register", json={
        "name": "Bad", "email": "not-an-email", "password": "x", "user_type": "Patient"
    })
    assert r.status_code == 422


@pytest.mark.parametrize("user", TEST_USERS)
def test_login_success(session, user):
    r = session.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and len(data["token"]) > 20
    assert data["user"]["email"] == user["email"]
    assert "password" not in data["user"]


def test_login_invalid_password(session):
    r = session.post(f"{API}/auth/login", json={"email": TEST_USERS[0]["email"], "password": "wrongpass"})
    assert r.status_code == 401


def test_login_nonexistent(session):
    r = session.post(f"{API}/auth/login", json={"email": "nobody@nope.com", "password": "x"})
    assert r.status_code == 401


@pytest.fixture(scope="module")
def auth_token(session):
    r = session.post(f"{API}/auth/login", json={
        "email": TEST_USERS[0]["email"], "password": TEST_USERS[0]["password"]
    })
    assert r.status_code == 200
    return r.json()["token"]


def test_me_with_bearer(session, auth_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"] == TEST_USERS[0]["email"]
    assert "user_id" in data


def test_me_no_auth():
    r = requests.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_me_invalid_token():
    r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert r.status_code == 401


def test_logout():
    r = requests.post(f"{API}/auth/logout")
    assert r.status_code == 200
    assert "Logged out" in r.json().get("message", "")


def test_translate_requires_auth():
    r = requests.post(f"{API}/translate", json={"text": "hello", "source_lang": "en", "target_lang": "fa"})
    assert r.status_code == 401


def test_translate_success(auth_token):
    r = requests.post(
        f"{API}/translate",
        headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
        json={"text": "Hello, how are you?", "source_lang": "en", "target_lang": "fa"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "translation" in data
    assert isinstance(data["translation"], str) and len(data["translation"]) > 0


def test_google_session_invalid():
    r = requests.post(f"{API}/auth/google/session", json={"session_id": "invalid_session_xyz"})
    # Should fail with 400 since session_id is invalid
    assert r.status_code == 400

"""Phase 6 (FINAL) backend tests: HIPAA/GDPR/KVKK encryption + Anonymous public reviews + Featured Quote.

Covers:
- PUT/GET /api/profile: Patient blood_type & chronic_illnesses encrypted at rest, decrypted in response
- GET /api/profile/{user_id} as non-owner: Patient profile_data redacted to {}
- POST /api/chat/{id}/message: AI chat content encrypted at rest, decrypted on GET for owner, 403 for non-owner
- POST /api/reviews: comment encrypted at rest, decrypted in response
- GET /api/reviews/user/{id}: comments decrypted
- GET /api/reviews/public/{id}: NEW - reviewer_id/name stripped, reviewer_type='Anonymous', sorted desc, featured_quote populated
- POST/PUT /api/appointments: notes encrypted at rest, decrypted in response
- PUT /api/reviews/featured-quote/{id}: Premium-gated (402), Doctor/Pharmacy-only (403), 4-5 star only (400), 404 if not yours
- DELETE /api/reviews/featured-quote
- Raw MongoDB doc inspection: encrypted strings begin with 'enc-v1:'
"""
import asyncio
import os
import uuid
import pytest
import requests

# --- Backend URL ---
_ENV_URL = os.environ.get('REACT_APP_BACKEND_URL')
if not _ENV_URL:
    _env_file = '/app/frontend/.env'
    if os.path.exists(_env_file):
        with open(_env_file) as fh:
            for line in fh:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    _ENV_URL = line.split('=', 1)[1].strip()
                    break
assert _ENV_URL, "REACT_APP_BACKEND_URL must be set"
BASE_URL = _ENV_URL.rstrip('/')
API = f"{BASE_URL}/api"

# --- MongoDB direct access for at-rest verification ---
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

_MONGO_URL = None
_DB_NAME = None
_env_be = '/app/backend/.env'
if os.path.exists(_env_be):
    with open(_env_be) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith('MONGO_URL='):
                _MONGO_URL = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('DB_NAME='):
                _DB_NAME = line.split('=', 1)[1].strip().strip('"')
assert _MONGO_URL and _DB_NAME, "MONGO_URL and DB_NAME must be set in /app/backend/.env"

ENC_PREFIX = "enc-v1:"


def _run(coro):
    """Run an async coro in sync test code."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _get_raw_doc(collection: str, query: dict):
    client = AsyncIOMotorClient(_MONGO_URL)
    try:
        db = client[_DB_NAME]
        return await db[collection].find_one(query)
    finally:
        client.close()


# --- Test users (idempotent register + login) ---
USERS = {
    "doctor": {"name": "Test Doctor", "email": "doctor@test.com", "password": "Doctor123!", "user_type": "Doctor"},
    "patient": {"name": "Test Patient", "email": "patient@test.com", "password": "Patient123!", "user_type": "Patient"},
    "pharmacy": {"name": "Test Pharmacy", "email": "pharmacy@test.com", "password": "Pharmacy123!", "user_type": "Pharmacy"},
    "engineer": {"name": "Test Engineer", "email": "engineer@test.com", "password": "Engineer123!", "user_type": "Biomedical Engineer"},
}


def _register_or_login(user):
    r = requests.post(f"{API}/auth/register", json=user, timeout=20)
    assert r.status_code in (200, 400), f"register {user['email']}: {r.status_code} {r.text}"
    lr = requests.post(f"{API}/auth/login",
                       json={"email": user["email"], "password": user["password"]},
                       timeout=20)
    assert lr.status_code == 200, f"login {user['email']}: {lr.status_code} {lr.text}"
    data = lr.json()
    return data["token"], data["user"]


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role, u in USERS.items():
        tok, user = _register_or_login(u)
        out[role] = {
            "token": tok,
            "user_id": user["user_id"],
            "user": user,
            "headers": {"Authorization": f"Bearer {tok}"},
        }
    return out


# ====================================================================
# 1. PATIENT PHI ENCRYPTION AT REST
# ====================================================================
def test_patient_profile_phi_encrypted_at_rest_and_decrypted_in_response(tokens):
    """PUT /profile encrypts blood_type + chronic_illnesses at rest. Raw doc has enc-v1: prefix."""
    headers = tokens["patient"]["headers"]
    patient_id = tokens["patient"]["user_id"]

    plaintext_blood = f"O+_{uuid.uuid4().hex[:4]}"
    plaintext_illnesses = ["TEST_Diabetes_Type2", "TEST_Hypertension"]

    payload = {
        "profile_data": {
            "blood_type": plaintext_blood,
            "chronic_illnesses": plaintext_illnesses,
        }
    }
    r = requests.put(f"{API}/profile", json=payload, headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # API response must be DECRYPTED (plaintext)
    assert body["profile_data"]["blood_type"] == plaintext_blood
    assert body["profile_data"]["chronic_illnesses"] == plaintext_illnesses

    # Raw MongoDB doc must have ENCRYPTED PHI
    raw = asyncio.run(_get_raw_doc("users", {"user_id": patient_id}))
    assert raw is not None, "patient user doc not found in DB"
    pdata = raw.get("profile_data", {})
    assert isinstance(pdata.get("blood_type"), str), "blood_type missing in raw doc"
    assert pdata["blood_type"].startswith(ENC_PREFIX), \
        f"blood_type NOT encrypted at rest: {pdata['blood_type']!r}"
    assert pdata["blood_type"] != plaintext_blood
    assert isinstance(pdata.get("chronic_illnesses"), list)
    for item in pdata["chronic_illnesses"]:
        assert item.startswith(ENC_PREFIX), f"chronic_illnesses element NOT encrypted: {item!r}"


def test_get_profile_returns_decrypted_phi_for_owner(tokens):
    """GET /profile decrypts PHI for the owning patient."""
    r = requests.get(f"{API}/profile", headers=tokens["patient"]["headers"], timeout=10)
    assert r.status_code == 200
    pdata = r.json().get("profile_data", {})
    # No enc-v1: should ever leak to API consumers
    if pdata.get("blood_type"):
        assert not pdata["blood_type"].startswith(ENC_PREFIX), "PHI leaked encrypted on GET /profile"
    if pdata.get("chronic_illnesses"):
        for it in pdata["chronic_illnesses"]:
            assert not it.startswith(ENC_PREFIX), "chronic_illnesses leaked encrypted"


def test_get_public_patient_profile_redacts_phi_to_empty(tokens):
    """GET /profile/{patient_id} as non-owner returns profile_data == {}."""
    patient_id = tokens["patient"]["user_id"]
    r = requests.get(f"{API}/profile/{patient_id}", headers=tokens["doctor"]["headers"], timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("profile_data") == {}, f"PHI not redacted for non-owner: {body.get('profile_data')!r}"
    # Email/phone should also not be there (existing redaction)
    assert "email" not in body
    assert "phone" not in body


def test_profile_update_idempotent_re_encrypt_no_double_wrap(tokens):
    """Re-saving an unchanged PHI field should not double-encrypt (encrypt_phi is idempotent on enc-v1: input)."""
    headers = tokens["patient"]["headers"]
    # First read decrypted, then PUT it back as-is — backend should encrypt the plaintext fresh.
    g = requests.get(f"{API}/profile", headers=headers, timeout=10).json()
    pdata = g.get("profile_data", {})
    r = requests.put(f"{API}/profile", json={"profile_data": pdata}, headers=headers, timeout=15)
    assert r.status_code == 200
    # Now read raw doc - blood_type should still be a single-layer enc-v1: (not enc-v1:enc-v1:...)
    raw = asyncio.run(_get_raw_doc("users", {"user_id": tokens["patient"]["user_id"]}))
    bt = raw["profile_data"].get("blood_type")
    if bt:
        assert bt.startswith(ENC_PREFIX)
        # Should not contain the prefix twice
        assert bt.count(ENC_PREFIX) == 1, f"Double-encrypted: {bt!r}"


# ====================================================================
# 2. AI CHAT MESSAGE ENCRYPTION
# ====================================================================
@pytest.fixture(scope="module")
def patient_chat(tokens):
    """Start one symptom chat for the patient and send one message. Cached."""
    h = tokens["patient"]["headers"]
    # start
    r = requests.post(f"{API}/chat/start",
                      json={"chat_type": "symptom", "title": "TEST_Phase6_Chat"},
                      headers=h, timeout=15)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    user_text = f"TEST_Phase6 I have a headache {uuid.uuid4().hex[:6]}"
    last_err = None
    ai_response = ""
    for _attempt in range(2):
        try:
            m = requests.post(f"{API}/chat/{session_id}/message",
                              json={"text": user_text},
                              headers=h, timeout=120)
            if m.status_code == 200:
                ai_response = m.json().get("response", "")
                if isinstance(ai_response, str) and len(ai_response) > 0:
                    break
            last_err = f"{m.status_code} {m.text[:200]}"
        except Exception as e:
            last_err = str(e)
    assert ai_response, f"chat message failed after retries: {last_err}"
    return {"session_id": session_id, "user_text": user_text, "ai_response": ai_response}


def test_chat_messages_encrypted_at_rest(tokens, patient_chat):
    """db.chat_sessions.messages[*].content begins with enc-v1: (both user & assistant)."""
    raw = asyncio.run(_get_raw_doc("chat_sessions", {"session_id": patient_chat["session_id"]}))
    assert raw is not None, "chat session not found in DB"
    msgs = raw.get("messages", [])
    assert len(msgs) >= 2, f"expected >=2 messages, got {len(msgs)}"
    for m in msgs:
        c = m.get("content")
        assert isinstance(c, str) and c.startswith(ENC_PREFIX), f"chat content NOT encrypted: {c!r}"
        # The plaintext must NOT be in the raw doc
    raw_str = str(msgs)
    assert patient_chat["user_text"] not in raw_str, "plaintext user text leaked in raw chat doc"


def test_chat_get_decrypts_for_owner(tokens, patient_chat):
    """GET /chat/{id} returns decrypted messages to the owning patient."""
    r = requests.get(f"{API}/chat/{patient_chat['session_id']}",
                     headers=tokens["patient"]["headers"], timeout=15)
    assert r.status_code == 200
    msgs = r.json().get("messages", [])
    assert len(msgs) >= 2
    contents = [m["content"] for m in msgs]
    # No enc-v1: leakage in API response
    for c in contents:
        assert not c.startswith(ENC_PREFIX), "decryption did not happen on GET /chat/{id}"
    # The user text we sent should be present in decrypted form
    assert any(patient_chat["user_text"] in c for c in contents), \
        "user message not decrypted to original plaintext"


def test_chat_get_403_for_non_owner(tokens, patient_chat):
    """GET /chat/{id} as another user returns 403."""
    r = requests.get(f"{API}/chat/{patient_chat['session_id']}",
                     headers=tokens["doctor"]["headers"], timeout=10)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


# ====================================================================
# 3. REVIEW COMMENT ENCRYPTION
# ====================================================================
@pytest.fixture(scope="module")
def patient_review_of_doctor(tokens):
    """Patient creates a 5-star review of doctor. Cached for featured-quote tests."""
    comment = f"TEST_Phase6 Excellent doctor — very thorough {uuid.uuid4().hex[:6]}"
    payload = {
        "reviewee_id": tokens["doctor"]["user_id"],
        "rating": 5,
        "comment": comment,
        "tags": ["professional", "knowledgeable"],
    }
    r = requests.post(f"{API}/reviews", json=payload, headers=tokens["patient"]["headers"], timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["comment"] == comment, "review POST should return decrypted comment"
    return {"review_id": body["review_id"], "comment": comment, "rating": 5}


def test_review_comment_encrypted_at_rest(tokens, patient_review_of_doctor):
    raw = asyncio.run(_get_raw_doc("reviews", {"review_id": patient_review_of_doctor["review_id"]}))
    assert raw is not None
    c = raw.get("comment")
    assert isinstance(c, str) and c.startswith(ENC_PREFIX), f"review comment NOT encrypted at rest: {c!r}"
    assert patient_review_of_doctor["comment"] not in c


def test_get_reviews_by_user_decrypts(tokens, patient_review_of_doctor):
    """GET /reviews/user/{doctor_id} returns decrypted comments."""
    doctor_id = tokens["doctor"]["user_id"]
    r = requests.get(f"{API}/reviews/user/{doctor_id}", timeout=10)
    assert r.status_code == 200
    reviews = r.json().get("reviews", [])
    found = [rv for rv in reviews if rv.get("review_id") == patient_review_of_doctor["review_id"]]
    assert found, "review not present in /reviews/user response"
    assert found[0]["comment"] == patient_review_of_doctor["comment"]
    for rv in reviews:
        assert not (isinstance(rv.get("comment"), str) and rv["comment"].startswith(ENC_PREFIX)), \
            "encrypted comment leaked"


# ====================================================================
# 4. PUBLIC ANONYMOUS REVIEWS ENDPOINT
# ====================================================================
def test_public_reviews_strips_identity_and_anonymizes(tokens, patient_review_of_doctor):
    """GET /reviews/public/{doctor_id}: no reviewer_id/name, reviewer_type='Anonymous', sorted desc."""
    doctor_id = tokens["doctor"]["user_id"]
    r = requests.get(f"{API}/reviews/public/{doctor_id}", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == doctor_id
    assert body["user_type"] == "Doctor"
    assert "total_reviews" in body and "average_rating" in body
    reviews = body["reviews"]
    assert len(reviews) >= 1
    # Sorted desc by created_at
    created_ats = [rv.get("created_at", "") for rv in reviews]
    assert created_ats == sorted(created_ats, reverse=True), "reviews not sorted desc by created_at"
    for rv in reviews:
        assert "reviewer_id" not in rv, f"reviewer_id leaked: {rv}"
        assert "reviewer_name" not in rv, f"reviewer_name leaked: {rv}"
        assert rv.get("reviewer_type") == "Anonymous", f"reviewer_type not anonymized: {rv.get('reviewer_type')}"
        # Comments still decrypted
        if isinstance(rv.get("comment"), str):
            assert not rv["comment"].startswith(ENC_PREFIX)


def test_public_reviews_404_for_unknown_user():
    r = requests.get(f"{API}/reviews/public/unknown_user_{uuid.uuid4().hex[:8]}", timeout=10)
    assert r.status_code == 404


# ====================================================================
# 5. APPOINTMENT NOTES ENCRYPTION
# ====================================================================
def test_appointment_notes_encrypted_at_rest_and_updated(tokens):
    headers_p = tokens["patient"]["headers"]
    headers_d = tokens["doctor"]["headers"]
    note1 = f"TEST_Phase6 patient_note_{uuid.uuid4().hex[:6]} severe back pain"
    payload = {
        "doctor_id": tokens["doctor"]["user_id"],
        "scheduled_at": "2026-12-01T10:00:00+00:00",
        "appointment_type": "in_person",
        "notes": note1,
    }
    r = requests.post(f"{API}/appointments", json=payload, headers=headers_p, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    appt_id = body["appointment_id"]
    assert body["notes"] == note1, "POST /appointments should return decrypted notes"

    # Raw doc encrypted
    raw = asyncio.run(_get_raw_doc("appointments", {"appointment_id": appt_id}))
    assert raw["notes"].startswith(ENC_PREFIX), f"appointment notes NOT encrypted at rest: {raw['notes']!r}"
    assert note1 not in raw["notes"]

    # PUT notes update -> still encrypted at rest, decrypted in response
    note2 = f"TEST_Phase6 doctor_note_{uuid.uuid4().hex[:6]} prescribed ibuprofen"
    u = requests.put(f"{API}/appointments/{appt_id}",
                     json={"notes": note2}, headers=headers_d, timeout=15)
    assert u.status_code == 200, u.text
    assert u.json()["notes"] == note2

    raw2 = asyncio.run(_get_raw_doc("appointments", {"appointment_id": appt_id}))
    assert raw2["notes"].startswith(ENC_PREFIX)
    assert note2 not in raw2["notes"]


# ====================================================================
# 6. FEATURED QUOTE (Premium-gated)
# ====================================================================
def test_featured_quote_402_when_not_premium(tokens, patient_review_of_doctor):
    """Doctor without active subscription gets 402 on PUT /reviews/featured-quote/{id}."""
    # Ensure no active sub
    requests.post(f"{API}/subscriptions/cancel", headers=tokens["doctor"]["headers"], timeout=10)
    r = requests.put(f"{API}/reviews/featured-quote/{patient_review_of_doctor['review_id']}",
                     headers=tokens["doctor"]["headers"], timeout=10)
    assert r.status_code == 402, f"expected 402, got {r.status_code} {r.text}"


def test_featured_quote_403_for_non_doctor_pharmacy(tokens, patient_review_of_doctor):
    """Patient cannot set featured quote (403)."""
    r = requests.put(f"{API}/reviews/featured-quote/{patient_review_of_doctor['review_id']}",
                     headers=tokens["patient"]["headers"], timeout=10)
    assert r.status_code == 403


@pytest.fixture(scope="module")
def doctor_premium(tokens):
    """Subscribe doctor to Premium so featured-quote unlocks. Auto-cleanup after module."""
    r = requests.post(f"{API}/subscriptions/subscribe",
                      json={"plan": "featured_monthly", "mock_card_number": "4242424242424242"},
                      headers=tokens["doctor"]["headers"], timeout=15)
    assert r.status_code == 200, r.text
    yield
    # Teardown: cancel
    requests.post(f"{API}/subscriptions/cancel", headers=tokens["doctor"]["headers"], timeout=10)


def test_featured_quote_set_succeeds_when_premium(tokens, patient_review_of_doctor, doctor_premium):
    r = requests.put(f"{API}/reviews/featured-quote/{patient_review_of_doctor['review_id']}",
                     headers=tokens["doctor"]["headers"], timeout=10)
    assert r.status_code == 200, r.text
    assert r.json().get("review_id") == patient_review_of_doctor["review_id"]


def test_featured_quote_404_for_review_not_yours(tokens, doctor_premium):
    """Pharmacy is also premium-eligible, but a review_id that doesn't belong to them -> 404."""
    # Subscribe pharmacy temporarily
    requests.post(f"{API}/subscriptions/subscribe",
                  json={"plan": "featured_monthly"},
                  headers=tokens["pharmacy"]["headers"], timeout=15)
    try:
        # Use a random/non-existent review id
        bogus = f"review_{uuid.uuid4().hex[:12]}"
        r = requests.put(f"{API}/reviews/featured-quote/{bogus}",
                         headers=tokens["pharmacy"]["headers"], timeout=10)
        assert r.status_code == 404, r.text
    finally:
        requests.post(f"{API}/subscriptions/cancel",
                      headers=tokens["pharmacy"]["headers"], timeout=10)


def test_featured_quote_400_for_low_rating(tokens, doctor_premium):
    """A 3-star review cannot be featured (400)."""
    # Pharmacy reviews doctor with 3 stars (Pharmacy->Doctor allowed by review rules? Patient->Doctor is normal.)
    # Safer: create a 3-star review from patient. But patient already left a 5-star review.
    # Try a 2nd review from another role: Engineer can't review Doctor typically. Use patient with a second reviewee_id?
    # Easiest: create a 3-star review FROM patient TO pharmacy, then have pharmacy try to feature it.
    pharm_id = tokens["pharmacy"]["user_id"]
    r = requests.post(f"{API}/reviews",
                      json={"reviewee_id": pharm_id, "rating": 3,
                            "comment": "TEST_Phase6 mid review", "tags": []},
                      headers=tokens["patient"]["headers"], timeout=15)
    assert r.status_code == 200, r.text
    low_id = r.json()["review_id"]

    # subscribe pharmacy
    requests.post(f"{API}/subscriptions/subscribe",
                  json={"plan": "featured_monthly"},
                  headers=tokens["pharmacy"]["headers"], timeout=15)
    try:
        f = requests.put(f"{API}/reviews/featured-quote/{low_id}",
                         headers=tokens["pharmacy"]["headers"], timeout=10)
        assert f.status_code == 400, f"expected 400 for 3-star, got {f.status_code} {f.text}"
    finally:
        requests.post(f"{API}/subscriptions/cancel",
                      headers=tokens["pharmacy"]["headers"], timeout=10)


def test_public_reviews_includes_featured_quote(tokens, patient_review_of_doctor, doctor_premium):
    """After doctor sets featured quote, GET /reviews/public/{doctor_id} returns featured_quote populated & anonymized."""
    # Re-set (idempotent)
    requests.put(f"{API}/reviews/featured-quote/{patient_review_of_doctor['review_id']}",
                 headers=tokens["doctor"]["headers"], timeout=10)

    r = requests.get(f"{API}/reviews/public/{tokens['doctor']['user_id']}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    fq = body.get("featured_quote")
    assert fq is not None, "featured_quote should be populated"
    assert fq.get("review_id") == patient_review_of_doctor["review_id"]
    assert fq.get("rating") == 5
    assert fq.get("reviewer_type") == "Anonymous"
    assert "reviewer_id" not in fq
    assert "reviewer_name" not in fq
    assert fq.get("comment") == patient_review_of_doctor["comment"], "fq comment should be decrypted"


def test_featured_quote_delete(tokens, doctor_premium):
    """DELETE /reviews/featured-quote removes featured quote."""
    d = requests.delete(f"{API}/reviews/featured-quote",
                        headers=tokens["doctor"]["headers"], timeout=10)
    assert d.status_code == 200
    # Verify it's gone
    r = requests.get(f"{API}/reviews/public/{tokens['doctor']['user_id']}", timeout=10)
    assert r.status_code == 200
    assert r.json().get("featured_quote") is None


# ====================================================================
# 7. REGRESSION: PHI decryption error path
# ====================================================================
def test_encryption_idempotent_on_no_change_update(tokens):
    """PUT /profile with name only (no profile_data) doesn't corrupt the existing encrypted PHI."""
    headers = tokens["patient"]["headers"]
    r = requests.put(f"{API}/profile", json={"name": "Test Patient"},
                     headers=headers, timeout=15)
    assert r.status_code == 200
    # Subsequent GET still decrypts properly
    g = requests.get(f"{API}/profile", headers=headers, timeout=10)
    assert g.status_code == 200
    pdata = g.json().get("profile_data", {})
    if pdata.get("blood_type"):
        assert not pdata["blood_type"].startswith(ENC_PREFIX)
        assert pdata["blood_type"] != "[DECRYPTION_ERROR]"

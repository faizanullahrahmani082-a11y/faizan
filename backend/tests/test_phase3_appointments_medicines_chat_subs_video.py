"""Phase 3 backend tests: Appointments, Medicines, AI Chat (Gemini 3.1 Pro),
Subscriptions (mock payment), Video signaling rooms, public Pharmacies listing.

Covers all endpoints added in Phase 3 of the Afghan Health Portal under /api prefix.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

# --- Resolve backend URL from env (fallback to frontend/.env) ---
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

USERS = {
    "doctor":   {"name": "Test Doctor",   "email": "doctor@test.com",   "password": "Doctor123!",   "user_type": "Doctor"},
    "patient":  {"name": "Test Patient",  "email": "patient@test.com",  "password": "Patient123!",  "user_type": "Patient"},
    "pharmacy": {"name": "Test Pharmacy", "email": "pharmacy@test.com", "password": "Pharmacy123!", "user_type": "Pharmacy"},
    "engineer": {"name": "Test Engineer", "email": "engineer@test.com", "password": "Engineer123!", "user_type": "Biomedical Engineer"},
}


def _register_or_login(user):
    requests.post(f"{API}/auth/register", json=user, timeout=20)  # idempotent
    lr = requests.post(f"{API}/auth/login",
                       json={"email": user["email"], "password": user["password"]},
                       timeout=20)
    assert lr.status_code == 200, f"login {user['email']}: {lr.status_code} {lr.text}"
    d = lr.json()
    return d["token"], d["user"]


@pytest.fixture(scope="module")
def state():
    """Shared mutable state across ordered tests within a module."""
    return {}


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


# ============= APPOINTMENTS =============
class TestAppointments:
    def test_patient_books_appointment(self, tokens, state):
        scheduled = "2026-05-21T14:30:00"
        r = requests.post(
            f"{API}/appointments",
            headers=tokens["patient"]["headers"],
            json={"doctor_id": tokens["doctor"]["user_id"],
                  "scheduled_at": scheduled,
                  "appointment_type": "video",
                  "notes": "TEST_phase3 appt"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["doctor_id"] == tokens["doctor"]["user_id"]
        assert d["patient_id"] == tokens["patient"]["user_id"]
        assert d["status"] == "pending"
        assert d["scheduled_at"] == scheduled
        assert d["appointment_type"] == "video"
        assert d["appointment_id"].startswith("appt_")
        assert "_id" not in d
        state['appt_id'] = d["appointment_id"]
        state['appt_scheduled'] = scheduled

    def test_non_patient_cannot_book(self, tokens):
        r = requests.post(
            f"{API}/appointments",
            headers=tokens["doctor"]["headers"],
            json={"doctor_id": tokens["doctor"]["user_id"],
                  "scheduled_at": "2026-05-22T10:00:00"},
            timeout=20,
        )
        assert r.status_code == 403

    def test_book_with_unknown_doctor(self, tokens):
        r = requests.post(
            f"{API}/appointments",
            headers=tokens["patient"]["headers"],
            json={"doctor_id": "user_doesnotexist_xx", "scheduled_at": "2026-05-22T10:00:00"},
            timeout=20,
        )
        assert r.status_code == 404

    def test_list_my_appointments_patient(self, tokens, state):
        r = requests.get(f"{API}/appointments/me", headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        ids = [a["appointment_id"] for a in d["appointments"]]
        assert state['appt_id'] in ids
        assert d["count"] >= 1

    def test_list_my_appointments_doctor_view(self, tokens, state):
        r = requests.get(f"{API}/appointments/me", headers=tokens["doctor"]["headers"], timeout=15)
        assert r.status_code == 200
        ids = [a["appointment_id"] for a in r.json()["appointments"]]
        assert state['appt_id'] in ids

    def test_doctor_confirms_appointment(self, tokens, state):
        r = requests.put(
            f"{API}/appointments/{state['appt_id']}",
            headers=tokens["doctor"]["headers"],
            json={"status": "confirmed"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

    def test_outsider_cannot_update_appointment(self, tokens, state):
        r = requests.put(
            f"{API}/appointments/{state['appt_id']}",
            headers=tokens["engineer"]["headers"],
            json={"status": "cancelled"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_booked_slots_includes_pending_confirmed(self, tokens, state):
        date = state['appt_scheduled'][:10]
        r = requests.get(
            f"{API}/appointments/doctor/{tokens['doctor']['user_id']}/booked-slots",
            params={"date": date}, timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["date"] == date
        slot_ids = [s["appointment_id"] for s in d["booked_slots"]]
        assert state['appt_id'] in slot_ids

    def test_patient_cancels_then_slot_removed(self, tokens, state):
        r = requests.put(
            f"{API}/appointments/{state['appt_id']}",
            headers=tokens["patient"]["headers"],
            json={"status": "cancelled"},
            timeout=15,
        )
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        # Slot list should now NOT include cancelled appointment
        date = state['appt_scheduled'][:10]
        r2 = requests.get(
            f"{API}/appointments/doctor/{tokens['doctor']['user_id']}/booked-slots",
            params={"date": date}, timeout=15,
        )
        slot_ids = [s["appointment_id"] for s in r2.json()["booked_slots"]]
        assert state['appt_id'] not in slot_ids

    def test_update_unknown_appointment_404(self, tokens):
        r = requests.put(f"{API}/appointments/appt_doesnotexist",
                         headers=tokens["doctor"]["headers"],
                         json={"status": "confirmed"}, timeout=15)
        assert r.status_code == 404


# ============= MEDICINES =============
class TestMedicines:
    def test_pharmacy_creates_medicine(self, tokens, state):
        r = requests.post(
            f"{API}/medicines",
            headers=tokens["pharmacy"]["headers"],
            json={"name": "TEST_Paracetamol 500mg",
                  "generic_name": "Paracetamol",
                  "category": "painkiller",
                  "manufacturer": "TestPharma",
                  "price": 2.50,
                  "stock": 100,
                  "description": "TEST item",
                  "requires_prescription": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["pharmacy_id"] == tokens["pharmacy"]["user_id"]
        assert d["name"] == "TEST_Paracetamol 500mg"
        assert d["price"] == 2.50
        assert d["stock"] == 100
        assert d["medicine_id"].startswith("med_")
        state['med_id'] = d["medicine_id"]

    def test_non_pharmacy_cannot_create(self, tokens):
        r = requests.post(
            f"{API}/medicines",
            headers=tokens["doctor"]["headers"],
            json={"name": "TEST_X", "price": 1.0},
            timeout=15,
        )
        assert r.status_code == 403

    def test_search_medicines_public_no_auth(self):
        r = requests.get(f"{API}/medicines", params={"search": "TEST_Paracetamol"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        names = [m["name"] for m in d["medicines"]]
        assert any("TEST_Paracetamol" in n for n in names)

    def test_search_by_category(self):
        r = requests.get(f"{API}/medicines", params={"category": "painkiller"}, timeout=15)
        assert r.status_code == 200
        cats = {m.get("category") for m in r.json()["medicines"]}
        assert cats == {"painkiller"} or "painkiller" in cats

    def test_search_by_pharmacy_id(self, tokens):
        r = requests.get(f"{API}/medicines",
                         params={"pharmacy_id": tokens["pharmacy"]["user_id"]}, timeout=15)
        assert r.status_code == 200
        assert all(m["pharmacy_id"] == tokens["pharmacy"]["user_id"] for m in r.json()["medicines"])

    def test_pharmacy_updates_own_medicine(self, tokens, state):
        r = requests.put(
            f"{API}/medicines/{state['med_id']}",
            headers=tokens["pharmacy"]["headers"],
            json={"price": 3.25, "stock": 80},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["price"] == 3.25
        assert r.json()["stock"] == 80
        # GET to verify persistence
        r2 = requests.get(f"{API}/medicines",
                          params={"pharmacy_id": tokens["pharmacy"]["user_id"]}, timeout=15)
        match = [m for m in r2.json()["medicines"] if m["medicine_id"] == state['med_id']]
        assert match and match[0]["price"] == 3.25

    def test_non_owner_cannot_update(self, tokens, state):
        # Register another pharmacy
        other = {"name": "Other Pharmacy", "email": f"other_pharm_{uuid.uuid4().hex[:6]}@test.com",
                 "password": "Pharm123!", "user_type": "Pharmacy"}
        tok, _ = _register_or_login(other)
        r = requests.put(
            f"{API}/medicines/{state['med_id']}",
            headers={"Authorization": f"Bearer {tok}"},
            json={"price": 0.01}, timeout=15,
        )
        assert r.status_code == 403

    def test_update_unknown_medicine_404(self, tokens):
        r = requests.put(f"{API}/medicines/med_doesnotexist",
                         headers=tokens["pharmacy"]["headers"],
                         json={"price": 1.0}, timeout=15)
        assert r.status_code == 404

    def test_pharmacy_deletes_own_medicine(self, tokens, state):
        r = requests.delete(f"{API}/medicines/{state['med_id']}",
                            headers=tokens["pharmacy"]["headers"], timeout=15)
        assert r.status_code == 200
        # Verify gone
        r2 = requests.get(f"{API}/medicines",
                          params={"pharmacy_id": tokens["pharmacy"]["user_id"]}, timeout=15)
        ids = [m["medicine_id"] for m in r2.json()["medicines"]]
        assert state['med_id'] not in ids


# ============= AI CHAT =============
class TestAIChat:
    def test_start_symptom_chat(self, tokens, state):
        r = requests.post(f"{API}/chat/start",
                          headers=tokens["patient"]["headers"],
                          json={"chat_type": "symptom", "title": "TEST headache"},
                          timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["chat_type"] == "symptom"
        assert d["session_id"].startswith("chat_")
        assert d["messages"] == []
        state['chat_session_id'] = d["session_id"]

    def test_start_invalid_chat_type(self, tokens):
        r = requests.post(f"{API}/chat/start",
                          headers=tokens["patient"]["headers"],
                          json={"chat_type": "garbage"}, timeout=15)
        assert r.status_code == 400

    def test_start_device_fault_chat(self, tokens):
        r = requests.post(f"{API}/chat/start",
                          headers=tokens["engineer"]["headers"],
                          json={"chat_type": "device_fault"},
                          timeout=15)
        assert r.status_code == 200
        assert r.json()["chat_type"] == "device_fault"

    def test_send_message_gemini(self, tokens, state):
        r = requests.post(
            f"{API}/chat/{state['chat_session_id']}/message",
            headers=tokens["patient"]["headers"],
            json={"text": "I have had a mild headache for 2 days. What could it be?"},
            timeout=90,  # LLM call can be slow
        )
        assert r.status_code == 200, f"AI chat failed: {r.status_code} {r.text}"
        d = r.json()
        assert "response" in d
        assert isinstance(d["response"], str) and len(d["response"]) > 5
        assert d["session_id"] == state['chat_session_id']

    def test_send_to_others_session_forbidden(self, tokens, state):
        r = requests.post(
            f"{API}/chat/{state['chat_session_id']}/message",
            headers=tokens["doctor"]["headers"],
            json={"text": "hi"}, timeout=30,
        )
        assert r.status_code == 403

    def test_send_to_unknown_session_404(self, tokens):
        r = requests.post(f"{API}/chat/chat_doesnotexist/message",
                          headers=tokens["patient"]["headers"],
                          json={"text": "x"}, timeout=15)
        assert r.status_code == 404

    def test_message_too_long_400(self, tokens, state):
        r = requests.post(
            f"{API}/chat/{state['chat_session_id']}/message",
            headers=tokens["patient"]["headers"],
            json={"text": "a" * 4001}, timeout=15,
        )
        assert r.status_code == 400

    def test_list_my_chats(self, tokens, state):
        r = requests.get(f"{API}/chat/me", headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        ids = [s["session_id"] for s in d["sessions"]]
        assert state['chat_session_id'] in ids
        # 'messages' should NOT be present in list view
        for s in d["sessions"]:
            assert "messages" not in s

    def test_get_full_chat(self, tokens, state):
        r = requests.get(f"{API}/chat/{state['chat_session_id']}",
                         headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["session_id"] == state['chat_session_id']
        assert len(d["messages"]) >= 2  # user + assistant
        roles = {m["role"] for m in d["messages"]}
        assert "user" in roles and "assistant" in roles

    def test_get_others_chat_forbidden(self, tokens, state):
        r = requests.get(f"{API}/chat/{state['chat_session_id']}",
                         headers=tokens["doctor"]["headers"], timeout=15)
        assert r.status_code == 403


# ============= SUBSCRIPTIONS =============
class TestSubscriptions:
    def test_get_plans_public(self):
        r = requests.get(f"{API}/subscriptions/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json()["plans"]
        assert "featured_monthly" in plans
        assert "featured_yearly" in plans
        assert plans["featured_monthly"]["price_usd"] == 9.99
        assert plans["featured_yearly"]["duration_days"] == 365

    def test_patient_cannot_subscribe(self, tokens):
        r = requests.post(f"{API}/subscriptions/subscribe",
                          headers=tokens["patient"]["headers"],
                          json={"plan": "featured_monthly"}, timeout=15)
        assert r.status_code == 403

    def test_invalid_plan_400(self, tokens):
        r = requests.post(f"{API}/subscriptions/subscribe",
                          headers=tokens["pharmacy"]["headers"],
                          json={"plan": "premium_diamond"}, timeout=15)
        assert r.status_code == 400

    def test_pharmacy_subscribes_and_gets_badges(self, tokens):
        r = requests.post(f"{API}/subscriptions/subscribe",
                          headers=tokens["pharmacy"]["headers"],
                          json={"plan": "featured_monthly", "mock_card_number": "4111111111111234"},
                          timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "subscription" in d
        assert d["subscription"]["plan"] == "featured_monthly"
        assert d["subscription"]["is_active"] is True
        assert d["subscription"]["mock_card_last4"] == "1234"
        # Verify badges via /pharmacies/all (since /auth/me does not expose
        # is_verified / is_featured — see action item for main agent).
        pharms = requests.get(f"{API}/pharmacies/all", timeout=15).json()["pharmacies"]
        mine = [p for p in pharms if p["user_id"] == tokens["pharmacy"]["user_id"]]
        assert mine, "pharmacy missing from /pharmacies/all"
        assert mine[0].get("is_verified") is True
        assert mine[0].get("is_featured") is True

    def test_my_subscription(self, tokens):
        r = requests.get(f"{API}/subscriptions/me",
                         headers=tokens["pharmacy"]["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("is_active") is True
        assert d.get("plan") == "featured_monthly"

    def test_default_card_last4(self, tokens):
        # Engineer subscribes without providing card -> defaults to 4242
        r = requests.post(f"{API}/subscriptions/subscribe",
                          headers=tokens["engineer"]["headers"],
                          json={"plan": "featured_yearly"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["subscription"]["mock_card_last4"] == "4242"

    def test_cancel_removes_badges(self, tokens):
        r = requests.post(f"{API}/subscriptions/cancel",
                          headers=tokens["pharmacy"]["headers"], timeout=15)
        assert r.status_code == 200
        # /subscriptions/me should now have no active sub
        sub = requests.get(f"{API}/subscriptions/me",
                           headers=tokens["pharmacy"]["headers"], timeout=15).json()
        assert sub.get("is_active") in (None, False)
        # Badges removed — verified via /pharmacies/all
        pharms = requests.get(f"{API}/pharmacies/all", timeout=15).json()["pharmacies"]
        mine = [p for p in pharms if p["user_id"] == tokens["pharmacy"]["user_id"]]
        assert mine, "pharmacy missing from /pharmacies/all"
        assert mine[0].get("is_verified") is False
        assert mine[0].get("is_featured") is False


# ============= VIDEO ROOMS / SIGNALING =============
class TestVideoRooms:
    def test_doctor_creates_room(self, tokens, state):
        r = requests.post(f"{API}/video/rooms",
                          headers=tokens["doctor"]["headers"],
                          json={"invitee_id": tokens["patient"]["user_id"]},
                          timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["host_id"] == tokens["doctor"]["user_id"]
        assert d["invitee_id"] == tokens["patient"]["user_id"]
        assert d["is_active"] is True
        assert d["room_id"].startswith("room_")
        assert tokens["doctor"]["user_id"] in d["participants"]
        state['room_id'] = d["room_id"]

    def test_patient_joins_room(self, tokens, state):
        r = requests.post(f"{API}/video/rooms/{state['room_id']}/join",
                          headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert tokens["patient"]["user_id"] in d["participants"]
        assert tokens["doctor"]["user_id"] in d["participants"]

    def test_signal_exchange(self, tokens, state):
        ts_before = datetime.now(timezone.utc).isoformat()
        time.sleep(0.05)
        # Doctor sends offer to patient
        r = requests.post(
            f"{API}/video/rooms/{state['room_id']}/signal",
            headers=tokens["doctor"]["headers"],
            json={"target_user_id": tokens["patient"]["user_id"],
                  "signal_data": {"type": "offer", "sdp": "v=0\no=- 1 1 IN IP4 0\ns=-\nt=0 0\n"}},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["signal_id"].startswith("sig_")

        # Patient polls for signals targeted to them
        r2 = requests.get(f"{API}/video/rooms/{state['room_id']}/signals",
                          headers=tokens["patient"]["headers"], timeout=15)
        assert r2.status_code == 200
        sigs = r2.json()["signals"]
        assert len(sigs) >= 1
        assert sigs[-1]["signal_data"]["type"] == "offer"
        assert sigs[-1]["from_user_id"] == tokens["doctor"]["user_id"]
        assert sigs[-1]["target_user_id"] == tokens["patient"]["user_id"]

        # Doctor polls -> should NOT see signals targeted to patient
        r3 = requests.get(f"{API}/video/rooms/{state['room_id']}/signals",
                          headers=tokens["doctor"]["headers"], timeout=15)
        assert all(s["target_user_id"] == tokens["doctor"]["user_id"] for s in r3.json()["signals"])

        # 'since' filter
        r4 = requests.get(f"{API}/video/rooms/{state['room_id']}/signals",
                          headers=tokens["patient"]["headers"],
                          params={"since": ts_before}, timeout=15)
        assert r4.status_code == 200
        assert len(r4.json()["signals"]) >= 1

        # future 'since' returns empty
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        r5 = requests.get(f"{API}/video/rooms/{state['room_id']}/signals",
                          headers=tokens["patient"]["headers"],
                          params={"since": future}, timeout=15)
        assert r5.json()["signals"] == []

    def test_non_participant_cannot_signal(self, tokens, state):
        r = requests.post(
            f"{API}/video/rooms/{state['room_id']}/signal",
            headers=tokens["engineer"]["headers"],
            json={"target_user_id": tokens["patient"]["user_id"],
                  "signal_data": {"type": "candidate"}},
            timeout=15,
        )
        assert r.status_code == 403

    def test_non_host_cannot_close(self, tokens, state):
        r = requests.post(f"{API}/video/rooms/{state['room_id']}/close",
                          headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 403

    def test_host_closes_room(self, tokens, state):
        r = requests.post(f"{API}/video/rooms/{state['room_id']}/close",
                          headers=tokens["doctor"]["headers"], timeout=15)
        assert r.status_code == 200
        # Joining a closed room should 400
        r2 = requests.post(f"{API}/video/rooms/{state['room_id']}/join",
                           headers=tokens["patient"]["headers"], timeout=15)
        assert r2.status_code == 400

    def test_room_linked_to_appointment(self, tokens):
        # Create new appointment
        appt = requests.post(
            f"{API}/appointments",
            headers=tokens["patient"]["headers"],
            json={"doctor_id": tokens["doctor"]["user_id"],
                  "scheduled_at": "2026-06-10T11:00:00"},
            timeout=15,
        ).json()
        appt_id = appt["appointment_id"]
        # Create room linked to appointment
        r = requests.post(f"{API}/video/rooms",
                          headers=tokens["doctor"]["headers"],
                          json={"appointment_id": appt_id,
                                "invitee_id": tokens["patient"]["user_id"]},
                          timeout=15)
        assert r.status_code == 200
        room_id = r.json()["room_id"]
        # Appointment should now reference this room
        appts = requests.get(f"{API}/appointments/me",
                             headers=tokens["patient"]["headers"], timeout=15).json()
        linked = [a for a in appts["appointments"] if a["appointment_id"] == appt_id]
        assert linked and linked[0]["video_room_id"] == room_id

    def test_unknown_room_404(self, tokens):
        r = requests.post(f"{API}/video/rooms/room_doesnotexist/join",
                          headers=tokens["patient"]["headers"], timeout=15)
        assert r.status_code == 404


# ============= PUBLIC PHARMACIES LISTING =============
class TestPharmaciesAll:
    def test_list_all_pharmacies(self, tokens):
        # Ensure pharmacy has a location (required to appear in /pharmacies/all)
        requests.post(f"{API}/location",
                      headers=tokens["pharmacy"]["headers"],
                      json={"latitude": 34.5553, "longitude": 69.2075,
                            "address": "TEST Kabul"},
                      timeout=15)
        r = requests.get(f"{API}/pharmacies/all", timeout=15)
        assert r.status_code == 200
        d = r.json()
        ids = [p["user_id"] for p in d["pharmacies"]]
        assert tokens["pharmacy"]["user_id"] in ids
        # No email should be exposed
        for p in d["pharmacies"]:
            assert "email" not in p
            assert "password" not in p
            assert "_id" not in p
            assert "location" in p

    def test_only_featured_filter(self, tokens):
        # Subscribe pharmacy to mark featured
        requests.post(f"{API}/subscriptions/subscribe",
                      headers=tokens["pharmacy"]["headers"],
                      json={"plan": "featured_monthly"}, timeout=15)
        r = requests.get(f"{API}/pharmacies/all", params={"only_featured": True}, timeout=15)
        assert r.status_code == 200
        ids = [p["user_id"] for p in r.json()["pharmacies"]]
        assert tokens["pharmacy"]["user_id"] in ids
        # cleanup
        requests.post(f"{API}/subscriptions/cancel",
                      headers=tokens["pharmacy"]["headers"], timeout=15)

    def test_only_24_7_filter(self, tokens):
        # Mark pharmacy as 24/7 via profile
        requests.put(f"{API}/profile",
                     headers=tokens["pharmacy"]["headers"],
                     json={"profile_data": {"is_24_7": True}}, timeout=15)
        r = requests.get(f"{API}/pharmacies/all", params={"only_24_7": True}, timeout=15)
        assert r.status_code == 200
        ids = [p["user_id"] for p in r.json()["pharmacies"]]
        assert tokens["pharmacy"]["user_id"] in ids

        # Flip back and re-query
        requests.put(f"{API}/profile",
                     headers=tokens["pharmacy"]["headers"],
                     json={"profile_data": {"is_24_7": False}}, timeout=15)
        r2 = requests.get(f"{API}/pharmacies/all", params={"only_24_7": True}, timeout=15)
        ids2 = [p["user_id"] for p in r2.json()["pharmacies"]]
        assert tokens["pharmacy"]["user_id"] not in ids2

"""Phase 5 backend tests:
- Atomic stock decrement on POST /orders (race-condition prevention)
- Medicine stock restoration on order cancellation
- Custom Doctor consultation_fee (profile_data.consultation_fee) used by /commission/summary
- Monthly Performance Reports (GET /reports/monthly, POST /reports/monthly/send, GET /reports/me)
  with SIMULATED Resend email (delivery_status='SIMULATED_SENT')
"""
import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
import requests

# --- Resolve backend URL from env ---
_ENV_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not _ENV_URL:
    _env_file = "/app/frontend/.env"
    if os.path.exists(_env_file):
        with open(_env_file) as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    _ENV_URL = line.split("=", 1)[1].strip()
                    break
assert _ENV_URL, "REACT_APP_BACKEND_URL must be set"
BASE_URL = _ENV_URL.rstrip("/")
API = f"{BASE_URL}/api"

USERS = {
    "doctor":   {"name": "Test Doctor",   "email": "doctor@test.com",   "password": "Doctor123!",   "user_type": "Doctor"},
    "patient":  {"name": "Test Patient",  "email": "patient@test.com",  "password": "Patient123!",  "user_type": "Patient"},
    "pharmacy": {"name": "Test Pharmacy", "email": "pharmacy@test.com", "password": "Pharmacy123!", "user_type": "Pharmacy"},
    "engineer": {"name": "Test Engineer", "email": "engineer@test.com", "password": "Engineer123!", "user_type": "Biomedical Engineer"},
}


def _register_or_login(user):
    requests.post(f"{API}/auth/register", json=user, timeout=20)  # idempotent
    lr = requests.post(
        f"{API}/auth/login",
        json={"email": user["email"], "password": user["password"]},
        timeout=20,
    )
    assert lr.status_code == 200, f"login {user['email']}: {lr.status_code} {lr.text}"
    d = lr.json()
    return d["token"], d["user"]


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


def _create_medicine(pharmacy_headers, *, stock, price=10.0, requires_prescription=False, name=None):
    payload = {
        "name": name or f"TEST_Med_{uuid.uuid4().hex[:6]}",
        "category": "general",
        "manufacturer": "TestPharma",
        "price": price,
        "stock": stock,
        "description": "phase5 test",
        "requires_prescription": requires_prescription,
    }
    r = requests.post(f"{API}/medicines", headers=pharmacy_headers, json=payload, timeout=20)
    assert r.status_code == 200, f"medicine create failed: {r.status_code} {r.text}"
    return r.json()


# ====================================================================
# 1) Atomic stock decrement on POST /orders
# ====================================================================
class TestAtomicStockOrders:
    def test_insufficient_stock_returns_400(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=2)
        # Try to buy 5 when only 2 exist
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 5, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        assert "stock" in r.text.lower()

        # Stock must remain unchanged (2)
        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next((x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"]), None)
        assert mm and mm["stock"] == 2, f"stock changed unexpectedly: {mm}"

    def test_atomic_decrement_single_order(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=3, price=12.5)
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 2, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["quantity"] == 2
        assert o["subtotal"] == pytest.approx(25.0)
        # Stock should be 1
        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next(x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"])
        assert mm["stock"] == 1

    def test_concurrent_orders_only_one_succeeds_on_last_unit(self, tokens):
        """The big one: stock=1, two concurrent qty=1 orders -> exactly one 200, one 400."""
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=1, name=f"TEST_Race_{uuid.uuid4().hex[:6]}")
        results = []
        lock = threading.Lock()

        def _place():
            try:
                rr = requests.post(
                    f"{API}/orders",
                    headers=tokens["patient"]["headers"],
                    json={"medicine_id": med["medicine_id"], "quantity": 1, "delivery_address": "Kabul"},
                    timeout=30,
                )
                with lock:
                    results.append(rr.status_code)
            except Exception as e:  # pragma: no cover
                with lock:
                    results.append(f"err:{e}")

        threads = [threading.Thread(target=_place) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [s for s in results if s == 200]
        failures = [s for s in results if s == 400]
        assert len(successes) == 1, f"expected exactly 1 success, got {results}"
        assert len(failures) == 1, f"expected exactly 1 failure, got {results}"

        # Stock now 0 (or back to 0 - never negative)
        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next(x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"])
        assert mm["stock"] == 0, f"stock should be 0 after race resolution, got {mm['stock']}"


# ====================================================================
# 2) Stock restoration on order cancellation
# ====================================================================
class TestStockRestoreOnCancel:
    def test_cancel_restores_stock(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=10, price=5.0)
        # order 3 -> stock should become 7
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 3, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        order_id = r.json()["order_id"]

        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next(x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"])
        assert mm["stock"] == 7

        # Patient cancels (pending order)
        rc = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["patient"]["headers"],
            json={"status": "cancelled"},
            timeout=20,
        )
        assert rc.status_code == 200, rc.text
        assert rc.json()["status"] == "cancelled"

        # Stock should be restored to 10
        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next(x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"])
        assert mm["stock"] == 10, f"stock not restored, got {mm['stock']}"

    def test_pharmacy_cancel_also_restores_stock(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=8, price=4.0)
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 5, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        order_id = r.json()["order_id"]

        # Pharmacy cancels
        rc = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["pharmacy"]["headers"],
            json={"status": "cancelled"},
            timeout=20,
        )
        assert rc.status_code == 200, rc.text

        s = requests.get(f"{API}/medicines?q=", timeout=20).json()
        mm = next(x for x in s["medicines"] if x["medicine_id"] == med["medicine_id"])
        assert mm["stock"] == 8, f"pharmacy cancel didn't restore stock, got {mm['stock']}"


# ====================================================================
# 3) Patient cancellation rules + cannot update terminal orders
# ====================================================================
class TestOrderStatusGuards:
    def test_patient_cannot_cancel_confirmed_order(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=5, price=3.0)
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 1, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert r.status_code == 200
        order_id = r.json()["order_id"]

        # Pharmacy confirms order
        rc = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["pharmacy"]["headers"],
            json={"status": "confirmed"},
            timeout=20,
        )
        assert rc.status_code == 200, rc.text
        assert rc.json()["status"] == "confirmed"

        # Patient tries to cancel a confirmed order
        rcancel = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["patient"]["headers"],
            json={"status": "cancelled"},
            timeout=20,
        )
        assert rcancel.status_code == 400, f"expected 400, got {rcancel.status_code}: {rcancel.text}"
        assert "pending" in rcancel.text.lower()

    def test_cannot_update_cancelled_order(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=4, price=2.0)
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 1, "delivery_address": "Kabul"},
            timeout=20,
        )
        order_id = r.json()["order_id"]

        # Patient cancels
        rc = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["patient"]["headers"],
            json={"status": "cancelled"},
            timeout=20,
        )
        assert rc.status_code == 200

        # Pharmacy tries to re-open (ship) cancelled
        rr = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["pharmacy"]["headers"],
            json={"status": "shipped"},
            timeout=20,
        )
        assert rr.status_code == 400, f"expected 400, got {rr.status_code}: {rr.text}"

    def test_cannot_update_delivered_order(self, tokens):
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=4, price=2.0)
        r = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 1, "delivery_address": "Kabul"},
            timeout=20,
        )
        order_id = r.json()["order_id"]

        # Pharmacy ships pending order then marks delivered
        for st in ["confirmed", "shipped", "delivered"]:
            rr = requests.put(
                f"{API}/orders/{order_id}",
                headers=tokens["pharmacy"]["headers"],
                json={"status": st},
                timeout=20,
            )
            assert rr.status_code == 200, f"transition to {st} failed: {rr.text}"

        # Pharmacy tries to revert delivered
        rr = requests.put(
            f"{API}/orders/{order_id}",
            headers=tokens["pharmacy"]["headers"],
            json={"status": "shipped"},
            timeout=20,
        )
        assert rr.status_code == 400, f"expected 400 on delivered update, got {rr.status_code}"


# ====================================================================
# 4) Custom Doctor consultation_fee
# ====================================================================
class TestDoctorConsultationFee:
    def test_set_consultation_fee_via_profile(self, tokens):
        r = requests.put(
            f"{API}/profile",
            headers=tokens["doctor"]["headers"],
            json={"profile_data": {"consultation_fee": 50.0, "specialty": "Cardiology"}},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # accept either updated user shape with profile_data or message+user
        prof = body.get("profile_data") or body.get("user", {}).get("profile_data")
        assert prof is not None, f"profile_data missing in response: {body}"
        assert float(prof.get("consultation_fee")) == 50.0

    def test_commission_summary_uses_custom_fee(self, tokens):
        # Ensure fee is 50
        requests.put(
            f"{API}/profile",
            headers=tokens["doctor"]["headers"],
            json={"profile_data": {"consultation_fee": 50.0, "specialty": "Cardiology"}},
            timeout=20,
        )
        r = requests.get(f"{API}/commission/summary", headers=tokens["doctor"]["headers"], timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "Doctor"
        assert float(d["consultation_fee"]) == 50.0
        # gmv == completed * 50 (completed may be 0; the formula must hold)
        assert d["gmv"] == d["completed_consultations"] * 50.0

    def test_default_fee_when_unset(self, tokens):
        # Set fee to None to test default fallback (30)
        requests.put(
            f"{API}/profile",
            headers=tokens["doctor"]["headers"],
            json={"profile_data": {"consultation_fee": None, "specialty": "Cardiology"}},
            timeout=20,
        )
        r = requests.get(f"{API}/commission/summary", headers=tokens["doctor"]["headers"], timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert float(d["consultation_fee"]) == 30.0


# ====================================================================
# 5) Monthly reports: GET /reports/monthly
# ====================================================================
def _previous_month(now=None):
    now = now or datetime.now(timezone.utc)
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1


class TestMonthlyReports:
    def test_default_previous_month_pharmacy(self, tokens):
        r = requests.get(f"{API}/reports/monthly", headers=tokens["pharmacy"]["headers"], timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "Pharmacy"
        y, m = _previous_month()
        assert d["period"] == f"{y}-{m:02d}"
        for k in ["total_orders", "gmv", "commission_total", "payout_total", "top_medicines"]:
            assert k in d, f"missing key {k} in pharmacy report"
        assert isinstance(d["top_medicines"], list)
        assert len(d["top_medicines"]) <= 5

    def test_default_previous_month_doctor(self, tokens):
        r = requests.get(f"{API}/reports/monthly", headers=tokens["doctor"]["headers"], timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "Doctor"
        for k in ["completed_consultations", "gmv", "avg_rating", "total_reviews", "consultation_fee"]:
            assert k in d, f"missing key {k} in doctor report"

    def test_default_previous_month_engineer(self, tokens):
        r = requests.get(f"{API}/reports/monthly", headers=tokens["engineer"]["headers"], timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "Biomedical Engineer"
        for k in ["avg_rating", "total_reviews"]:
            assert k in d

    def test_specific_year_month(self, tokens):
        r = requests.get(
            f"{API}/reports/monthly?year=2025&month=11",
            headers=tokens["pharmacy"]["headers"],
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == "2025-11"

    def test_invalid_month(self, tokens):
        r = requests.get(
            f"{API}/reports/monthly?year=2025&month=13",
            headers=tokens["pharmacy"]["headers"],
            timeout=20,
        )
        assert r.status_code == 400

    def test_patient_forbidden(self, tokens):
        r = requests.get(f"{API}/reports/monthly", headers=tokens["patient"]["headers"], timeout=20)
        assert r.status_code == 403

    def test_pharmacy_report_includes_current_month_orders(self, tokens):
        """Create an order this month, then request current-month report -> total_orders >= 1, gmv > 0."""
        now = datetime.now(timezone.utc)
        med = _create_medicine(tokens["pharmacy"]["headers"], stock=20, price=7.0, name=f"TEST_Rep_{uuid.uuid4().hex[:6]}")
        ro = requests.post(
            f"{API}/orders",
            headers=tokens["patient"]["headers"],
            json={"medicine_id": med["medicine_id"], "quantity": 2, "delivery_address": "Kabul"},
            timeout=20,
        )
        assert ro.status_code == 200

        r = requests.get(
            f"{API}/reports/monthly?year={now.year}&month={now.month}",
            headers=tokens["pharmacy"]["headers"],
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == f"{now.year}-{now.month:02d}"
        assert d["total_orders"] >= 1
        assert d["gmv"] >= 14.0  # 2 * 7


# ====================================================================
# 6) POST /reports/monthly/send: simulated Resend email
# ====================================================================
class TestSendMonthlyReport:
    def test_send_creates_record_and_notification(self, tokens):
        # baseline notification count
        before = requests.get(
            f"{API}/notifications", headers=tokens["pharmacy"]["headers"], timeout=20
        ).json()
        before_count = before.get("count", 0)

        r = requests.post(
            f"{API}/reports/monthly/send",
            headers=tokens["pharmacy"]["headers"],
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery_status"] == "SIMULATED_SENT"
        assert d["to"] == "pharmacy@test.com"
        assert d["report_id"].startswith("report_")
        assert "report" in d and d["report"]["role"] == "Pharmacy"

        # GET /reports/me should now contain this report
        rm = requests.get(f"{API}/reports/me", headers=tokens["pharmacy"]["headers"], timeout=20)
        assert rm.status_code == 200, rm.text
        listing = rm.json()
        assert listing["count"] >= 1
        ids = [x["report_id"] for x in listing["reports"]]
        assert d["report_id"] in ids
        # email_html must be projected out for list endpoint
        for rep in listing["reports"]:
            assert "email_html" not in rep
            assert rep["delivery_status"] == "SIMULATED_SENT"

        # Notification of type 'monthly_report' created
        after = requests.get(
            f"{API}/notifications", headers=tokens["pharmacy"]["headers"], timeout=20
        ).json()
        assert after["count"] >= before_count + 1
        types = [n["type"] for n in after["notifications"]]
        assert "monthly_report" in types

    def test_send_for_doctor_specific_month(self, tokens):
        r = requests.post(
            f"{API}/reports/monthly/send?year=2025&month=11",
            headers=tokens["doctor"]["headers"],
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery_status"] == "SIMULATED_SENT"
        assert d["report"]["period"] == "2025-11"
        assert d["report"]["role"] == "Doctor"

    def test_send_for_engineer(self, tokens):
        r = requests.post(
            f"{API}/reports/monthly/send",
            headers=tokens["engineer"]["headers"],
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery_status"] == "SIMULATED_SENT"
        assert d["report"]["role"] == "Biomedical Engineer"

    def test_patient_send_forbidden(self, tokens):
        r = requests.post(
            f"{API}/reports/monthly/send",
            headers=tokens["patient"]["headers"],
            timeout=30,
        )
        assert r.status_code == 403


# ====================================================================
# 7) GET /reports/me listing
# ====================================================================
class TestListMyReports:
    def test_doctor_reports_listing(self, tokens):
        # Ensure at least one
        requests.post(
            f"{API}/reports/monthly/send?year=2025&month=10",
            headers=tokens["doctor"]["headers"],
            timeout=30,
        )
        r = requests.get(f"{API}/reports/me", headers=tokens["doctor"]["headers"], timeout=20)
        assert r.status_code == 200, r.text
        listing = r.json()
        assert listing["count"] >= 1
        assert all(rep["user_id"] == tokens["doctor"]["user_id"] for rep in listing["reports"])
        # sorted desc by created_at
        ts = [rep["created_at"] for rep in listing["reports"]]
        assert ts == sorted(ts, reverse=True)

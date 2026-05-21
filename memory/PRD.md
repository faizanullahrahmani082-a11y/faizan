# Afghan Health Portal - PRD

## Original Problem Statement
3-language (Pashto, Farsi/Dari, English) health application for Doctor/Patient/Pharmacy/Biomedical Engineer with full feature set: profile + GPS + reviews + appointments + medicines + AI assistant + maps + video calls + premium subscriptions + file uploads + notifications + doctor scheduling + medicine orders + commission tracking + monthly performance reports.

## Tech Stack
- **Backend**: FastAPI + Motor (MongoDB), JWT + Google OAuth, emergentintegrations (Gemini 3.1 Pro), Emergent Object Storage
- **Frontend**: React 19, React Router 7, Tailwind, Shadcn UI, Leaflet (maps), SimplePeer (WebRTC)
- **Languages**: EN (Outfit) / FA-DR / PS (Vazirmatn) with RTL support

## Implementation Status

### ✅ Phase 1 — Auth & Multilingual UI (20/20)
### ✅ Phase 2 — Database Architecture (52/52)
### ✅ Phase 3 — Core Features (99/99)
### ✅ Phase 4 — Object Storage + Schedule + Orders + Notifications + Commission (147/147)
### ✅ Phase 5 (Feb 2026) — Atomic Stock + Custom Fees + Monthly Reports
- **Atomic stock decrement** in POST /orders via `find_one_and_update` with stock filter (verified by 2-thread concurrent race test on stock=1)
- **Stock restoration** on order cancellation (both patient + pharmacy initiated)
- **Order state guards**: patient can only cancel pending; cannot reopen cancelled/delivered
- **Custom consultation_fee** on Doctor profile_data — handles 0.0 (charity) correctly
- **Monthly Performance Reports**:
  - Pharmacy: total_orders, gmv, commission, payout, top 5 medicines, cancelled count
  - Doctor: completed_consultations, gmv, avg_rating, total_reviews
  - Engineer: avg_rating, total_reviews
  - Defaults to previous month; specific year/month supported
- **Mock Resend Email**: POST /reports/monthly/send saves to db.monthly_reports + creates notification + logs (delivery_status='SIMULATED_SENT')
- **23/23 Phase 5 + 170/170 combined regression = 100%**

## MongoDB Collections (12 total)
| Collection | Purpose |
|------------|---------|
| `users` | Accounts with role-specific profile_data (incl. consultation_fee for Doctor) |
| `user_sessions` | Google OAuth sessions |
| `locations` | GeoJSON GPS |
| `reviews` | Ratings + tags |
| `appointments` | Bookings with 'completed' status (powers Doctor GMV) |
| `medicines` | Pharmacy catalog (atomic stock) |
| `chat_sessions` | AI chat history |
| `subscriptions` | Premium memberships (MOCK payment) |
| `video_rooms` | WebRTC signaling |
| `files` | Emergent Object Storage references |
| `schedules` | Doctor weekly templates |
| `orders` | Medicine orders + commission (atomic, with stock restoration) |
| `notifications` | HTTP-poll notifications |
| `monthly_reports` | Generated/sent reports (Resend simulated) |

## Commission & GMV Model (Investor Deck)
| Type | Rate | Source |
|------|------|--------|
| Medicine sale | 4% | Pharmacy orders (subtotal) |
| Consultation | 12% | Doctor completed video appointments × consultation_fee |

GMV dashboard: real-time per-user view. Monthly reports auto-aggregate.

## API Endpoints (Phase 5 additions)
- **Reports**: GET `/reports/monthly` (current/previous month), GET `/reports/monthly?year=&month=`, POST `/reports/monthly/send`, GET `/reports/me`
- **Atomic stock**: POST `/orders` (find_one_and_update with stock>=qty filter)
- **Stock restore**: PUT `/orders/{id}` (status=cancelled → $inc stock)

## Test Credentials (`/app/memory/test_credentials.md`)
- doctor@test.com / Doctor123!
- patient@test.com / Patient123!
- pharmacy@test.com / Pharmacy123!
- engineer@test.com / Engineer123!

## Prioritized Backlog

### P0 (Operational Hardening)
- [ ] Real Stripe integration to replace mock payment
- [ ] Order state-machine: disallow pending→delivered forward jumps
- [ ] De-duplicate monthly send by (user_id, period) upsert OR 1/day rate-limit
- [ ] HTML-escape user values in simulated email template (XSS in mock)

### P1 (Polish)
- [ ] Migrate video signaling: HTTP polling → WebSocket
- [ ] Pharmacy top_medicines: group by medicine_id (not name, for rename-safety)
- [ ] Query validators on /reports (year>=2024, 1<=month<=12)
- [ ] Doctor revenue recognition: completed_at vs created_at (PM decision)
- [ ] Admin platform-wide GMV dashboard
- [ ] FCM push notifications (mobile/browser)

### P2 (Tech Debt)
- [ ] Split server.py (~1965 lines) into routers/ submodules (auth, profile, orders, reports, etc.)
- [ ] Extract `_month_window(y, m)` helper (3 duplicate copies in report gens)
- [ ] Pagination across list endpoints
- [ ] TTL index on notifications (90-day cleanup)
- [ ] Cron to expire `is_featured` at `featured_until`
- [ ] $lookup aggregation in /pharmacies/all

## Known Minor Issues (Non-blocking, documented in iteration_5.json)
- Order status state-machine not enforced (pending→delivered jump allowed)
- Monthly send not deduped (spam-induced growth possible)
- top_medicines grouped by name (rename-unsafe)
- Email HTML not escaped (mock only — no XSS surface in production until Resend wired)
- Doctor revenue uses created_at (booking) not completion timestamp

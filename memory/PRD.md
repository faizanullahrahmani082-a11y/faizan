# Afghan Health Portal - PRD

## Original Problem Statement
3-language (Pashto, Farsi/Dari, English) health application for Doctor/Patient/Pharmacy/Biomedical Engineer with profile, GPS, reviews, appointments, medicines, AI assistant, maps, video calls, premium subscriptions, file uploads, notifications, doctor scheduling, medicine orders, and commission tracking.

## Tech Stack
- **Backend**: FastAPI + Motor (MongoDB), JWT + Google OAuth, emergentintegrations (Gemini 3.1 Pro), Emergent Object Storage
- **Frontend**: React 19, React Router 7, Tailwind, Shadcn UI, Leaflet (maps), SimplePeer (WebRTC)
- **Languages**: EN (Outfit) / FA-DR / PS (Vazirmatn) with RTL support

## Implementation Status

### ✅ Phase 1 — Auth & Multilingual UI (20/20 tests)
### ✅ Phase 2 — Database Architecture (32/32 + 20 regression)
### ✅ Phase 3 — Core Features (47/47 + 52 regression)
### ✅ Phase 4 (Feb 2026) — Object Storage + Schedule + Orders + Notifications + Commission
- **Emergent Object Storage**: Profile picture & prescription uploads (5MB, image/PDF MIME)
- **Doctor Weekly Schedule**: day_of_week + start/end time + slot duration template
- **Medicine Orders**: full purchase flow with stock decrement, prescription validation, auto-notifications
- **Commission Tracking**: 4% on medicine sales, 12% on doctor consultations (GMV dashboard)
- **HTTP Polling Notifications**: bell icon + unread count + auto-generated on order/appointment events
- **Profile Picture**: Avatar with upload UI in dashboard
- **Doctor Appointment Completion**: Doctor-only status='completed' (powers consultation GMV)
- **Prescription File Access Control**: Owner + linked pharmacy can view (PHI privacy)
- **48/48 Phase 4 + 147/147 combined regression = 100%**

## MongoDB Collections (10 total)
| Collection | Purpose |
|------------|---------|
| `users` | Accounts + role-specific profile_data + is_verified/is_featured |
| `user_sessions` | Google OAuth sessions |
| `locations` | GeoJSON GPS |
| `reviews` | Ratings + tags |
| `appointments` | Bookings (now with 'completed' status) |
| `medicines` | Pharmacy catalog |
| `chat_sessions` | AI chat history |
| `subscriptions` | Premium memberships |
| `video_rooms` | WebRTC signaling |
| `files` | Object Storage references |
| `schedules` | Doctor weekly templates |
| `orders` | Medicine orders + commission |
| `notifications` | Polling-based notifications |

## API Endpoints (Phase 4 additions)
- **Files**: POST `/upload`, GET `/files/{id}` (Bearer or `?auth=token`), DELETE `/files/{id}`
- **Schedule**: PUT `/schedule`, GET `/schedule/me`, GET `/schedule/{doctor_id}`
- **Orders**: POST `/orders`, GET `/orders/me`, PUT `/orders/{id}`
- **Notifications**: GET `/notifications` (poll), PUT `/notifications/{id}/read`, PUT `/notifications/read-all`
- **Commission**: GET `/commission/summary` (role-aware GMV)
- **Appointments**: PUT `/appointments/{id}` with `status='completed'` (doctor-only)

## Commission/GMV Model (Investor Deck)
- **Medicine sales**: 4% platform commission
- **Doctor video consultations**: 12% platform commission ($30/consultation default)
- **GMV Dashboard**: real-time per-user view of total sales, payout, and commission

## Test Credentials (`/app/memory/test_credentials.md`)
- doctor@test.com / Doctor123!
- patient@test.com / Patient123!
- pharmacy@test.com / Pharmacy123!
- engineer@test.com / Engineer123!

## Prioritized Backlog

### P0 (Next Sprint)
- [ ] Atomic stock decrement (race condition prevention)
- [ ] Real Stripe payment to replace mock subscription
- [ ] Doctor consultation_fee field on profile (replace $30 hardcode)
- [ ] Restore stock when orders cancelled
- [ ] Order status state-machine validation

### P1
- [ ] Migrate video signaling from HTTP polling to WebSocket
- [ ] Admin platform-wide GMV dashboard
- [ ] Doctor profile search by language preference
- [ ] FCM push notifications (browser/mobile)
- [ ] File upload: magic-byte content sniffing + streaming size limit
- [ ] Commission rates in `platform_config` collection (not hardcoded)

### P2 (Tech Debt)
- [ ] Split server.py (1700+ lines) into routers/ submodules
- [ ] Pagination across all list endpoints
- [ ] TTL index on notifications (90-day cleanup)
- [ ] Cron to expire `is_featured` at `featured_until`
- [ ] $lookup aggregation in /pharmacies/all
- [ ] CORS_ORIGINS hardening (no '*' with credentials)

## Known Minor Issues (Non-blocking)
- Stock decrement not atomic (race condition possible)
- Notification array grows unboundedly (need TTL)
- File size checked AFTER full read (DoS surface)
- Order status transitions not state-machine validated
- Cancelled orders don't restore stock

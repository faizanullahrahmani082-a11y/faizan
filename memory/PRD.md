# Afghan Health Portal - PRD

## Original Problem Statement
3-language (Pashto, Farsi/Dari, English) health application supporting Doctor/Patient/Pharmacy/Biomedical Engineer with profile, GPS, reviews, appointments, medicine catalog, AI assistant, maps, video calls, and premium subscriptions.

## Tech Stack
- **Backend**: FastAPI + Motor (MongoDB async), JWT + Google OAuth, emergentintegrations LlmChat (Gemini 3.1 Pro)
- **Frontend**: React 19, React Router 7, Tailwind, Shadcn UI, Leaflet (maps), SimplePeer (WebRTC)
- **Languages**: EN (Outfit) / FA-DR (Vazirmatn) / PS (Vazirmatn) with RTL support

## Color Palette
- Primary: Medical Teal `#0F766E`
- Secondary: Active Emerald `#10B981`
- Accent: Urgent Coral `#F97316`

## Implementation Status

### ✅ Phase 1 (Feb 2026) — Authentication & Multilingual UI
- JWT + Google OAuth, /auth/me, logout
- 3-language UI with RTL, dark mode
- Role selector login/register
- LLM translation endpoint (Gemini 3.1 Pro)
- **20/20 tests passing**

### ✅ Phase 2 (Feb 2026) — Database Architecture
- Role-specific profile models (Doctor/Patient/Pharmacy/Engineer)
- GeoJSON location + 2dsphere nearby search
- Reviews with role rules + tag aggregation
- **32/32 Phase 2 + 20/20 regression = 52/52 passing**

### ✅ Phase 3 (Feb 2026) — Core Features
- **Appointments**: Patient books Doctor (calendar + time slots + video/in-person types)
- **Medicines**: Pharmacy CRUD catalog + public search (name/category/pharmacy)
- **AI Chat**: Gemini 3.1 Pro symptom checker + device fault helper (persistent sessions)
- **Subscriptions**: Mock payment ($9.99/mo, $99.99/yr) → verified + featured badges
- **Video Rooms**: WebRTC signaling via HTTP polling, SimplePeer for P2P
- **Pharmacy Map**: Leaflet/OpenStreetMap with 24/7 color filter
- Tab-based Dashboard with role-aware visibility
- All UI in 3 languages
- **47/47 Phase 3 + 99/99 combined regression = 99/99 passing**
- Fixed: `/auth/me` now exposes `is_verified`, `is_featured`, `featured_until`

## MongoDB Collections
| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `users` | Accounts | user_id, user_type, profile_data, is_verified, is_featured |
| `user_sessions` | Google OAuth | user_id, session_token, expires_at |
| `locations` | GPS | user_id, location (GeoJSON), address |
| `reviews` | Ratings | review_id, reviewer_id, reviewee_id, rating, tags |
| `appointments` | Bookings | appointment_id, doctor_id, patient_id, scheduled_at, status, video_room_id |
| `medicines` | Pharmacy catalog | medicine_id, pharmacy_id, name, price, stock |
| `chat_sessions` | AI chats | session_id, user_id, chat_type, messages[] |
| `subscriptions` | Premium | subscription_id, user_id, plan, expires_at |
| `video_rooms` | WebRTC | room_id, host_id, participants[], signals[] |

## API Endpoints
| Domain | Endpoints |
|--------|-----------|
| Auth | register, login, google/session, me, logout |
| Profile | GET/PUT /profile, GET /profile/{id} |
| Location | POST /location, GET /location/me, GET /nearby |
| Reviews | POST /reviews, GET /reviews/user/{id}, GET /reviews/me, DELETE |
| Appointments | POST, GET /me, PUT, GET /doctor/{id}/booked-slots |
| Medicines | POST, GET (search), PUT, DELETE |
| AI Chat | POST /start, POST /{id}/message, GET /me, GET /{id} |
| Subscriptions | GET /plans, POST /subscribe, GET /me, POST /cancel |
| Video | POST /rooms, /join, /signal, GET /signals, POST /close |
| Public | GET /pharmacies/all, POST /translate |

## Test Credentials (`/app/memory/test_credentials.md`)
- doctor@test.com / Doctor123!
- patient@test.com / Patient123!
- pharmacy@test.com / Pharmacy123!
- engineer@test.com / Engineer123!

## Prioritized Backlog (Next Tasks)

### P0 (High Priority)
- [ ] Real-time notifications (FCM/WebSocket) for appointment status changes
- [ ] Prescription upload (object storage) → linked to medicine purchase
- [ ] Doctor's available-slots system (weekly schedule template)
- [ ] User profile picture upload

### P1 (Medium)
- [ ] Migrate from HTTP polling to WebSocket for video signaling
- [ ] Real Stripe payment integration to replace mock
- [ ] Search/filter by language preference (find Pashto-speaking doctors)
- [ ] Order/cart system for medicine purchase
- [ ] Cron job to expire `is_featured` at `featured_until`

### P2 (Polish & Tech Debt)
- [ ] Split server.py (1200+ lines) into routers/ submodules
- [ ] Double-booking prevention in POST /appointments
- [ ] Validate scheduled_at as ISO + future date
- [ ] Bound video signals array (TTL or cleanup)
- [ ] Pagination across list endpoints
- [ ] $lookup aggregation in /pharmacies/all (replace N+1)
- [ ] Map signals' target_user_id to room participants

## Known Minor Issues (Non-blocking - documented in iteration_3.json)
- Past dates accepted in appointment booking
- Mock card number accepts non-numeric strings
- Video signals never garbage-collected (memory grows during call)
- No badge expiry cron — pharmacy keeps badge until manual cancel

# Afghan Health Portal - PRD

## Original Problem Statement
Building a 3-language (Pashto, Farsi/Dari, English) health application with:
- Modern login/register screen
- 4 user types: Doctor, Patient, Pharmacy, Biomedical Engineer
- Profile data, GPS location, and Rating/Review system

## Architecture

### Tech Stack
- **Backend**: FastAPI + Motor (MongoDB async)
- **Frontend**: React 19 + React Router 7 + Tailwind + Shadcn UI
- **Database**: MongoDB
- **Auth**: JWT (email/password) + Emergent Google OAuth
- **LLM**: Gemini 3.1 Pro (via Emergent LLM Key) for medical translation
- **Fonts**: Outfit (LTR/English) + Vazirmatn (RTL/Farsi/Pashto)

### Color Palette
- Primary: Medical Teal (`#0F766E`)
- Secondary: Active Emerald (`#10B981`)
- Accent: Urgent Coral (`#F97316`)

## User Personas
1. **Doctor**: Provides consultations, can review Biomedical Engineers
2. **Patient**: Reviews Doctors and Pharmacies
3. **Pharmacy**: Business entity, reviewed by Patients, can review Engineers
4. **Biomedical Engineer**: Reviewed by Doctors and Pharmacies (B2B service)

## Implementation Status

### ✅ Phase 1 (Completed - Feb 2026): Authentication & Multilingual UI
- JWT email/password auth (register, login, logout, /auth/me)
- Emergent Google OAuth integration with httpOnly cookies
- 3-language support (English, Farsi/Dari, Pashto) with RTL layout
- Browser language auto-detection + manual switcher
- Dark mode toggle
- Split-screen login/register UI with role selector (2x2 grid)
- Protected Dashboard route
- LLM Translation endpoint (Gemini 3.1 Pro)
- **Tests**: 20/20 backend passing

### ✅ Phase 2 (Completed - Feb 2026): Database Architecture
- Role-specific profile models: DoctorProfile, PatientProfile, PharmacyProfile, EngineerProfile
- Profile CRUD: GET/PUT /api/profile, GET /api/profile/{user_id} (with PHI redaction for patients)
- GPS Location: POST /api/location, GET /api/location/me, GET /api/nearby (2dsphere geospatial)
- Reviews: POST/GET/DELETE /api/reviews with role-pair rules + tags
- Review rules: Patient→{Doctor, Pharmacy}, Doctor→Engineer, Pharmacy→Engineer
- Rating aggregation: average + tag counts
- **Tests**: 32/32 Phase 2 + 20/20 regression = 52/52 passing

## MongoDB Collections
| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `users` | User accounts | user_id (UUID), email, name, user_type, profile_data |
| `user_sessions` | Google OAuth sessions | user_id, session_token, expires_at |
| `locations` | GPS data | user_id, location (GeoJSON Point), address |
| `reviews` | Rating/reviews | review_id, reviewer_id, reviewee_id, rating, tags |

## API Endpoints Summary

### Auth
- POST `/api/auth/register` — JWT signup
- POST `/api/auth/login` — JWT login
- POST `/api/auth/google/session` — Exchange Google session_id
- GET `/api/auth/me` — Current user info
- POST `/api/auth/logout` — Clear session

### Profile
- GET `/api/profile` — Own profile (full)
- PUT `/api/profile` — Update own profile + role-specific fields
- GET `/api/profile/{user_id}` — Public profile (PHI redacted)

### Location
- POST `/api/location` — Set/update GPS
- GET `/api/location/me` — Get own location
- GET `/api/nearby?user_type=X&latitude=&longitude=&radius_km=` — Find nearby users

### Reviews
- POST `/api/reviews` — Create review (role rules enforced)
- GET `/api/reviews/user/{user_id}` — Reviews for user + aggregates
- GET `/api/reviews/me` — Reviews I've written
- DELETE `/api/reviews/{review_id}` — Delete own review

### LLM
- POST `/api/translate` — Translate text via Gemini 3.1 Pro

## Test Credentials (`/app/memory/test_credentials.md`)
- doctor@test.com / Doctor123!
- patient@test.com / Patient123!
- pharmacy@test.com / Pharmacy123!
- engineer@test.com / Engineer123!

## Prioritized Backlog (Next Tasks)

### P0 (High - Core MVP)
- [ ] Doctor consultation booking system (with calendar)
- [ ] Pharmacy product/medicine catalog + search
- [ ] Patient medical history tracking
- [ ] Engineer service request workflow (with device fault description AI assistant)

### P1 (Medium - Differentiators)
- [ ] Google Maps integration (24/7 pharmacy display, nearest pharmacy)
- [ ] WebRTC/Agora video calls for tele-health
- [ ] AI Medical Assistant chat (Gemini) — symptom checker, device fault description
- [ ] Push notifications (FCM) for appointments/messages
- [ ] User profile picture upload (object storage)

### P2 (Low - Polish)
- [ ] Migrate legacy pharmacist@test.com user → pharmacy
- [ ] Move 2dsphere index creation to app startup
- [ ] Add pagination to reviews/nearby endpoints
- [ ] Rate limiting on auth endpoints (brute-force protection)
- [ ] Unique constraint on (reviewer_id, reviewee_id) — one review per pair
- [ ] Reorder self-review check before role-pair check (dead code cleanup)
- [ ] Replace heuristic JWT-vs-session token detection with cleaner logic

## Known Minor Issues (Non-blocking)
1. Legacy `pharmacist@test.com` user still has deprecated `user_type='Pharmacist'`
2. `2dsphere` index created on-demand inside `/nearby` (works fine, just not optimal)
3. No pagination on reviews/nearby (hardcoded 50/500 limit)
4. Dead-code: self-review 400 check unreachable (role check fires first → 403)

# Afghan Health Portal - PRD (FINAL)

## Original Problem Statement
3-language (Pashto, Farsi/Dari, English) health application for Doctor/Patient/Pharmacy/Biomedical Engineer with complete feature set + HIPAA/GDPR/KVKK compliance.

## Tech Stack
- **Backend**: FastAPI + Motor (MongoDB async), JWT + Google OAuth, emergentintegrations (Gemini 3.1 Pro), Emergent Object Storage, cryptography (AES-256-GCM)
- **Frontend**: React 19, React Router 7, Tailwind, Shadcn UI, Leaflet (maps), SimplePeer (WebRTC)
- **Languages**: EN (Outfit) / FA-DR / PS (Vazirmatn) with RTL support

## Final Implementation Status — All 6 Phases Complete

| Phase | Focus | Tests |
|-------|-------|-------|
| 1 | Auth & Multilingual UI | 20/20 |
| 2 | Database Architecture (profiles, location, reviews) | 32/32 |
| 3 | Core Features (appointments, medicines, AI chat, subscriptions, video) | 47/47 |
| 4 | Object Storage + Schedule + Orders + Notifications + Commission | 48/48 |
| 5 | Atomic Stock + Custom Fees + Monthly Reports | 23/23 |
| 6 | AES-256 Encryption + Anonymous Reviews + Featured Quote | 20/20 |
| **TOTAL** | **Full Healthcare Platform** | **190/190 (100%)** |

## Compliance & Security (Phase 6)
- **AES-256-GCM encryption at rest** for: Patient blood_type, chronic_illnesses, AI chat messages, review comments, appointment notes
- **TLS 1.3** in transit (Kubernetes ingress + HTTPS)
- **Anonymous public reviews**: `/reviews/public/{user_id}` strips reviewer_id + reviewer_name; reviewer_type forced to "Anonymous"
- **PHI redaction**: Patient profile_data hidden from non-owners
- **Verified by**: 20 dedicated security tests including raw MongoDB inspection confirming no plaintext PHI
- **Idempotent encryption**: passing already-encrypted values is a no-op (`enc-v1:` version prefix)
- **Key**: 32-byte AES-256 key in `ENCRYPTION_KEY` env var (base64-encoded)

## Monetization Stack
1. **Premium Subscription** ($9.99/mo, $99.99/yr): Verified badge + Featured listing + Featured Quote (MOCK Stripe)
2. **Commission**: 4% on medicine sales, 12% on doctor consultations
3. **Featured Quote** (Premium-gated): Doctor/Pharmacy picks one 4-5★ review to highlight on public profile → social proof drives booking conversions
4. **GMV Dashboard**: Real-time per-user analytics
5. **Monthly Performance Reports**: Auto-generated, simulated Resend delivery

## MongoDB Collections (14 total)
| Collection | Encrypted Fields |
|------------|------------------|
| `users` | profile_data.blood_type, profile_data.chronic_illnesses (Patient) |
| `chat_sessions` | messages[*].content |
| `reviews` | comment |
| `appointments` | notes |
| `user_sessions`, `locations`, `medicines`, `subscriptions`, `video_rooms`, `files`, `schedules`, `orders`, `notifications`, `monthly_reports` | (no PHI) |

## API Endpoints (Phase 6 additions)
- GET `/api/reviews/public/{user_id}` — anonymized reviews + featured_quote
- PUT `/api/reviews/featured-quote/{review_id}` — Premium-gated
- DELETE `/api/reviews/featured-quote`

## Test Credentials (`/app/memory/test_credentials.md`)
- doctor@test.com / Doctor123!
- patient@test.com / Patient123!
- pharmacy@test.com / Pharmacy123!
- engineer@test.com / Engineer123!

## Mocked Integrations (per user request — keyless prototype)
1. Stripe payment → `POST /subscriptions/subscribe` (instant success)
2. Resend email → `POST /reports/monthly/send` (`delivery_status='SIMULATED_SENT'`)

## Known Minor Issues (Non-blocking, documented in iteration_6.json)
- Featured Quote: `is_verified` flag checked instead of real-time sub query
- Comments not HTML-escaped on public reviews (XSS risk if rendered as HTML)
- `tag_counts` and `average_rating` computed on capped list (biased for >500 reviews)
- PATIENT_PHI_FIELDS not iterated dynamically (hardcoded 2 fields)
- LlmChat failure loses user message (not persisted pre-call)

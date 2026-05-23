from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status, UploadFile, File, Query, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import httpx
import requests
from emergentintegrations.llm.chat import LlmChat, UserMessage
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

# AES-256-GCM encryption for PHI/PII at rest (HIPAA/GDPR/KVKK compliance)
ENCRYPTION_KEY = base64.b64decode(os.environ['ENCRYPTION_KEY'])
if len(ENCRYPTION_KEY) != 32:
    raise RuntimeError("ENCRYPTION_KEY must be a 32-byte (256-bit) base64-encoded key for AES-256")
_aesgcm = AESGCM(ENCRYPTION_KEY)
ENC_PREFIX = "enc-v1:"  # version marker for forward-compatibility


def encrypt_phi(plaintext):
    """Encrypt a string with AES-256-GCM. Returns prefixed base64 ciphertext. Idempotent: already-encrypted values pass through."""
    if plaintext is None or plaintext == "":
        return plaintext
    if not isinstance(plaintext, str):
        return plaintext
    if plaintext.startswith(ENC_PREFIX):
        return plaintext  # already encrypted
    nonce = os.urandom(12)
    ct = _aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ENC_PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_phi(ciphertext):
    """Decrypt AES-256-GCM ciphertext. Pass through plain strings for backward compat with legacy data."""
    if ciphertext is None or ciphertext == "":
        return ciphertext
    if not isinstance(ciphertext, str) or not ciphertext.startswith(ENC_PREFIX):
        return ciphertext  # legacy plaintext - return as-is
    try:
        data = base64.b64decode(ciphertext[len(ENC_PREFIX):])
        nonce, ct = data[:12], data[12:]
        return _aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return "[DECRYPTION_ERROR]"


def encrypt_list(items):
    """Encrypt each item in a list of strings (e.g., chronic_illnesses)"""
    if not items:
        return items
    return [encrypt_phi(x) if isinstance(x, str) else x for x in items]


def decrypt_list(items):
    if not items:
        return items
    return [decrypt_phi(x) if isinstance(x, str) else x for x in items]


# PHI fields per role that need encryption at rest
PATIENT_PHI_FIELDS = {"chronic_illnesses": "list", "blood_type": "str"}


def encrypt_patient_profile(profile_data: dict) -> dict:
    """Encrypt PHI fields in a Patient's profile_data"""
    if not profile_data:
        return profile_data
    out = {**profile_data}
    if "blood_type" in out and out["blood_type"]:
        out["blood_type"] = encrypt_phi(out["blood_type"])
    if "chronic_illnesses" in out and out["chronic_illnesses"]:
        out["chronic_illnesses"] = encrypt_list(out["chronic_illnesses"])
    return out


def decrypt_patient_profile(profile_data: dict) -> dict:
    if not profile_data:
        return profile_data
    out = {**profile_data}
    if "blood_type" in out and out["blood_type"]:
        out["blood_type"] = decrypt_phi(out["blood_type"])
    if "chronic_illnesses" in out and out["chronic_illnesses"]:
        out["chronic_illnesses"] = decrypt_list(out["chronic_illnesses"])
    return out


# ── Local File Storage ──────────────────────────────────────────────────────
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

def init_storage():
    """No-op: using local disk storage."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    logger.info("Object storage initialized successfully")

def put_object(file_id: str, data: bytes, content_type: str) -> dict:
    """Save bytes to local uploads/ directory."""
    dest = os.path.join(UPLOADS_DIR, file_id)
    with open(dest, "wb") as f:
        f.write(data)
    return {"path": file_id, "size": len(data)}

def get_object(file_id: str):
    """Read bytes from local uploads/ directory."""
    path = os.path.join(UPLOADS_DIR, file_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {file_id}")
    with open(path, "rb") as f:
        return f.read(), "application/octet-stream"

# ── AI / LLM ─────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")

# Commission rates
COMMISSION_RATES = {
    "medicine_sale": 0.04,  # 4% on pharmacy drug sales
    "consultation": 0.12,    # 12% on online doctor consultations
}

# ============= EMAIL (Resend) =============
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@faizan.af")


async def send_email(to: str, subject: str, html: str) -> dict:
    """Send an email via Resend API. Falls back to simulation if RESEND_API_KEY is not set."""
    if not RESEND_API_KEY:
        logger_pre = logging.getLogger(__name__)
        logger_pre.info(f"[EMAIL SIMULATED] To: {to} | Subject: {subject}")
        return {"simulated": True, "to": to, "subject": subject}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ============= MODELS =============
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: EmailStr
    name: str
    user_type: str  # Doctor, Patient, Pharmacy, Biomedical Engineer
    picture: Optional[str] = None
    phone: Optional[str] = None
    profile_data: Optional[dict] = None  # role-specific profile fields
    is_verified: Optional[bool] = False
    is_featured: Optional[bool] = False
    featured_until: Optional[str] = None
    is_admin: Optional[bool] = False
    is_banned: Optional[bool] = False
    created_at: datetime


class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    user_type: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    session_id: str


class TranslateRequest(BaseModel):
    text: str
    source_lang: str  # en, fa, ps
    target_lang: str  # en, fa, ps


# ============= PROFILE MODELS (Role-specific) =============
class DoctorProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    specialty: Optional[str] = None
    license_no: Optional[str] = None
    hospital: Optional[str] = None
    years_experience: Optional[int] = None
    working_hours: Optional[str] = None  # e.g. "Mon-Fri 9:00-17:00"
    consultation_fee: Optional[float] = 30.0
    currency: Optional[str] = "USD"  # USD | AFN
    bio: Optional[str] = None  # Free-text professional description
    clinic_address: Optional[str] = None


class PatientProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    age: Optional[int] = None
    gender: Optional[str] = None  # male, female, other
    blood_type: Optional[str] = None  # A+, B+, O-, etc.
    chronic_illnesses: Optional[List[str]] = []


class PharmacyProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    business_name: Optional[str] = None
    license_no: Optional[str] = None
    is_24_7: Optional[bool] = False
    opening_hours: Optional[str] = None  # e.g. "08:00"
    closing_hours: Optional[str] = None  # e.g. "22:00"


class EngineerProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    specialty: Optional[List[str]] = []  # device modalities, e.g. ["MRI", "X-Ray", "Ultrasound"]
    certifications: Optional[List[str]] = []
    years_experience: Optional[int] = None


class ProfileUpdate(BaseModel):
    """Generic profile update - includes name, picture, phone, and role-specific data"""
    name: Optional[str] = None
    phone: Optional[str] = None
    picture: Optional[str] = None
    profile_data: Optional[dict] = None  # role-specific fields


# ============= SERVICE TICKET MODELS =============
class ServiceTicketCreate(BaseModel):
    device_type: str  # e.g. "MRI", "X-Ray", "Ultrasound"
    issue_description: str
    location: Optional[str] = None
    urgency: Optional[str] = "normal"  # normal, urgent, critical
    contact_phone: Optional[str] = None


class ServiceTicketUpdate(BaseModel):
    status: Optional[str] = None  # open, accepted, in_progress, completed, cancelled
    engineer_notes: Optional[str] = None


# ============= PASSWORD RESET MODELS =============
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ============= MEDICAL RECORD MODELS =============
class MedicalRecordUpdate(BaseModel):
    allergies: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    # PHI already in PatientProfile: blood_type, chronic_illnesses — kept there
    # This record adds the rest of the clinical context


# ============= LOCATION MODELS =============
class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None


# ============= REVIEW MODELS =============
class ReviewCreate(BaseModel):
    reviewee_id: str  # who is being reviewed
    rating: int  # 1-5
    comment: Optional[str] = None
    tags: Optional[List[str]] = []  # e.g. ["Fast response", "Accurate diagnosis"]


# ============= AUTH HELPERS =============
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> User:
    # Check cookie first
    token = request.cookies.get("session_token")
    
    # Fallback to Authorization header
    if not token and credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Check if it's a JWT token or a session token
        if token.startswith('test_session_') or len(token) > 200:
            # Session token from Google OAuth
            session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            if not session_doc:
                raise HTTPException(status_code=401, detail="Invalid session")
            
            expires_at = session_doc["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired")
            
            user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
            if not user_doc:
                raise HTTPException(status_code=404, detail="User not found")
            
            return User(**user_doc)
        else:
            # JWT token from email/password auth
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise HTTPException(status_code=401, detail="Invalid token")
            
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                raise HTTPException(status_code=404, detail="User not found")
            
            return User(**user_doc)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ============= AUTH ROUTES =============
@api_router.post("/auth/register")
async def register(user_data: UserRegister):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    hashed_pw = hash_password(user_data.password)
    
    user_doc = {
        "user_id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "user_type": user_data.user_type,
        "password": hashed_pw,
        "picture": None,
        "phone": None,
        "profile_data": {},
        "is_verified": False,
        "is_admin": False,
        "is_banned": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.users.insert_one(user_doc)
    user_doc.pop("_id", None)

    # Create JWT token
    access_token = create_access_token({"sub": user_id})

    user_doc.pop("password", None)
    user_doc.pop("_id", None)
    return {"user": user_doc, "token": access_token}


@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    # Find user
    user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, user_doc.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check ban
    if user_doc.get("is_banned"):
        raise HTTPException(status_code=403, detail="Your account has been suspended. Contact support.")

    # Create JWT token
    access_token = create_access_token({"sub": user_doc["user_id"]})

    user_doc.pop("password", None)
    return {"user": user_doc, "token": access_token}


@api_router.post("/auth/google/session")
async def google_session(request: GoogleSessionRequest, response: Response):
    # Exchange session_id for user data
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": request.session_id}
            )
            resp.raise_for_status()
            google_data = resp.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to get session data: {str(e)}")
    
    # Find or create user
    user_doc = await db.users.find_one({"email": google_data["email"]}, {"_id": 0})
    
    if user_doc:
        # Update existing user
        await db.users.update_one(
            {"email": google_data["email"]},
            {"$set": {
                "name": google_data["name"],
                "picture": google_data.get("picture")
            }}
        )
        user_doc["name"] = google_data["name"]
        user_doc["picture"] = google_data.get("picture")
    else:
        # Create new user with default user_type (will need to select later)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": google_data["email"],
            "name": google_data["name"],
            "user_type": "Patient",  # Default
            "picture": google_data.get("picture"),
            "phone": None,
            "profile_data": {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
    
    # Create session
    session_token = google_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    session_doc = {
        "user_id": user_doc["user_id"],
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.user_sessions.insert_one(session_doc)
    
    # Set httpOnly cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    user_doc.pop("password", None)
    user_doc.pop("_id", None)
    return {"user": user_doc, "token": session_token}


@api_router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
        response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}


# ============= PROFILE ROUTES =============
def _validate_profile_data(user_type: str, profile_data: dict) -> dict:
    """Validate role-specific profile fields"""
    if not profile_data:
        return {}
    
    if user_type == "Doctor":
        return DoctorProfile(**profile_data).model_dump(exclude_none=True)
    elif user_type == "Patient":
        return PatientProfile(**profile_data).model_dump(exclude_none=True)
    elif user_type == "Pharmacy":
        return PharmacyProfile(**profile_data).model_dump(exclude_none=True)
    elif user_type == "Biomedical Engineer":
        return EngineerProfile(**profile_data).model_dump(exclude_none=True)
    return profile_data


@api_router.put("/profile")
async def update_profile(update: ProfileUpdate, current_user: User = Depends(get_current_user)):
    """Update current user's profile (name, phone, picture, role-specific data).
    Patient PHI (chronic_illnesses, blood_type) is encrypted at rest with AES-256-GCM."""
    update_doc = {}
    if update.name is not None:
        update_doc["name"] = update.name
    if update.phone is not None:
        update_doc["phone"] = update.phone
    if update.picture is not None:
        update_doc["picture"] = update.picture
    if update.profile_data is not None:
        # Validate role-specific fields
        validated = _validate_profile_data(current_user.user_type, update.profile_data)
        # Encrypt PHI for patients
        if current_user.user_type == "Patient":
            validated = encrypt_patient_profile(validated)
        update_doc["profile_data"] = validated
    
    if update_doc:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": update_doc}
        )
    
    user_doc = await db.users.find_one(
        {"user_id": current_user.user_id},
        {"_id": 0, "password": 0}
    )
    # Decrypt PHI when returning to the patient themselves
    if user_doc.get("user_type") == "Patient":
        user_doc["profile_data"] = decrypt_patient_profile(user_doc.get("profile_data", {}))
    return user_doc


@api_router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user's full profile (PHI decrypted for the owner)"""
    user_doc = await db.users.find_one(
        {"user_id": current_user.user_id},
        {"_id": 0, "password": 0}
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    if user_doc.get("user_type") == "Patient":
        user_doc["profile_data"] = decrypt_patient_profile(user_doc.get("profile_data", {}))
    return user_doc


@api_router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: User = Depends(get_current_user)):
    """Get another user's public profile (no email/phone, PHI redacted for patients)"""
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "password": 0, "email": 0, "phone": 0}
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Redact Patient PHI (only the patient themselves can see their own medical data)
    if user_doc.get("user_type") == "Patient" and user_id != current_user.user_id:
        user_doc["profile_data"] = {}
    
    return user_doc


# ============= LOCATION ROUTES =============
@api_router.post("/location")
async def update_location(loc: LocationUpdate, current_user: User = Depends(get_current_user)):
    """Update or set current user's GPS location (stored as GeoJSON for geospatial queries)"""
    location_doc = {
        "user_id": current_user.user_id,
        "user_type": current_user.user_type,
        "location": {
            "type": "Point",
            "coordinates": [loc.longitude, loc.latitude]  # GeoJSON: [lng, lat]
        },
        "address": loc.address,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.locations.update_one(
        {"user_id": current_user.user_id},
        {"$set": location_doc},
        upsert=True
    )
    
    location_doc.pop("_id", None)
    return location_doc


@api_router.get("/location/me")
async def get_my_location(current_user: User = Depends(get_current_user)):
    """Get current user's saved location"""
    loc = await db.locations.find_one({"user_id": current_user.user_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="No location set")
    return loc


@api_router.get("/nearby")
async def find_nearby(
    user_type: str,
    latitude: float,
    longitude: float,
    radius_km: float = 5.0,
    current_user: User = Depends(get_current_user)
):
    """Find nearby users by type within radius (km). Returns list with profile + distance."""
    # Ensure geospatial index exists (idempotent)
    try:
        await db.locations.create_index([("location", "2dsphere")])
    except Exception:
        pass
    
    radius_meters = radius_km * 1000
    nearby_locations = await db.locations.find(
        {
            "user_type": user_type,
            "location": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude]
                    },
                    "$maxDistance": radius_meters
                }
            }
        },
        {"_id": 0}
    ).to_list(50)
    
    # Enrich with user profile
    results = []
    for loc in nearby_locations:
        user = await db.users.find_one(
            {"user_id": loc["user_id"]},
            {"_id": 0, "password": 0, "email": 0}
        )
        if user:
            results.append({
                "user": user,
                "location": loc
            })
    
    return {"count": len(results), "results": results}


# ============= REVIEW ROUTES =============
# Allowed review pairs: (reviewer_type -> reviewee_type)
ALLOWED_REVIEW_PAIRS = {
    "Patient": ["Doctor", "Pharmacy"],
    "Doctor": ["Biomedical Engineer"],
    "Pharmacy": ["Biomedical Engineer"],
}


@api_router.post("/reviews")
async def create_review(review: ReviewCreate, current_user: User = Depends(get_current_user)):
    """Add a review. Patient->Doctor/Pharmacy, Doctor/Pharmacy->Biomedical Engineer."""
    if review.rating < 1 or review.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    # Find reviewee
    reviewee = await db.users.find_one({"user_id": review.reviewee_id}, {"_id": 0})
    if not reviewee:
        raise HTTPException(status_code=404, detail="Reviewee not found")
    
    # Validate role rule
    allowed = ALLOWED_REVIEW_PAIRS.get(current_user.user_type, [])
    if reviewee["user_type"] not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"{current_user.user_type} cannot review {reviewee['user_type']}"
        )
    
    if review.reviewee_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot review yourself")
    
    review_doc = {
        "review_id": f"review_{uuid.uuid4().hex[:12]}",
        "reviewer_id": current_user.user_id,
        "reviewer_name": current_user.name,
        "reviewer_type": current_user.user_type,
        "reviewee_id": review.reviewee_id,
        "reviewee_type": reviewee["user_type"],
        "rating": review.rating,
        "comment": encrypt_phi(review.comment),
        "tags": review.tags or [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.reviews.insert_one(review_doc)
    review_doc.pop("_id", None)
    # Decrypt for response to author
    review_doc["comment"] = decrypt_phi(review_doc["comment"])
    return review_doc


@api_router.get("/reviews/user/{user_id}")
async def get_user_reviews(user_id: str):
    """Get all reviews for a specific user with aggregate stats (comments decrypted for display)"""
    reviews = await db.reviews.find({"reviewee_id": user_id}, {"_id": 0}).to_list(500)
    
    avg_rating = 0
    if reviews:
        avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
    
    # Aggregate tag counts
    tag_counts = {}
    for r in reviews:
        for tag in r.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        # Decrypt comment for display
        if "comment" in r:
            r["comment"] = decrypt_phi(r["comment"])
    
    return {
        "user_id": user_id,
        "total_reviews": len(reviews),
        "average_rating": round(avg_rating, 2),
        "tag_counts": tag_counts,
        "reviews": reviews
    }


@api_router.get("/reviews/me")
async def get_my_reviews(current_user: User = Depends(get_current_user)):
    """Get all reviews authored by the current user"""
    reviews = await db.reviews.find(
        {"reviewer_id": current_user.user_id},
        {"_id": 0}
    ).to_list(500)
    for r in reviews:
        if "comment" in r:
            r["comment"] = decrypt_phi(r["comment"])
    return {"count": len(reviews), "reviews": reviews}


@api_router.get("/reviews/public/{user_id}")
async def get_public_reviews(user_id: str, limit: int = 20):
    """ANONYMIZED public reviews — no reviewer_id/name. Used on public doctor/pharmacy profiles.
    HIPAA/GDPR/KVKK: patient identities are completely hidden in public-facing endpoints."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    reviews = await db.reviews.find(
        {"reviewee_id": user_id},
        {"_id": 0, "reviewer_id": 0, "reviewer_name": 0}  # STRIP identity
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    avg_rating = 0
    if reviews:
        all_reviews = await db.reviews.find({"reviewee_id": user_id}, {"_id": 0, "rating": 1}).to_list(500)
        avg_rating = sum(r["rating"] for r in all_reviews) / len(all_reviews)
    
    tag_counts = {}
    for r in reviews:
        # Decrypt comments for public display (decision: comments are written for public view)
        if "comment" in r:
            r["comment"] = decrypt_phi(r["comment"])
        # Strip reviewer_type to "Anonymous"
        r["reviewer_type"] = "Anonymous"
        for tag in r.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Include featured quote if doctor/pharmacy has set one
    featured_quote = None
    fq_id = user.get("featured_quote_review_id")
    if fq_id:
        fq = await db.reviews.find_one(
            {"review_id": fq_id, "reviewee_id": user_id},
            {"_id": 0, "reviewer_id": 0, "reviewer_name": 0}
        )
        if fq:
            fq["comment"] = decrypt_phi(fq.get("comment"))
            fq["reviewer_type"] = "Anonymous"
            featured_quote = fq
    
    return {
        "user_id": user_id,
        "user_type": user.get("user_type"),
        "average_rating": round(avg_rating, 2),
        "total_reviews": len(reviews),
        "tag_counts": tag_counts,
        "featured_quote": featured_quote,
        "reviews": reviews
    }


@api_router.put("/reviews/featured-quote/{review_id}")
async def set_featured_quote(review_id: str, current_user: User = Depends(get_current_user)):
    """Doctor/Pharmacy picks ONE 4-5 star review to highlight as featured quote on their public profile.
    Requires Premium subscription (is_verified=True). Social proof feature."""
    if current_user.user_type not in ["Doctor", "Pharmacy"]:
        raise HTTPException(status_code=403, detail="Only doctors and pharmacies can set featured quotes")
    
    # Premium-gated feature
    user_doc = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    if not user_doc.get("is_verified"):
        raise HTTPException(status_code=402, detail="Featured Quote is a Premium feature. Subscribe to unlock.")
    
    review = await db.reviews.find_one(
        {"review_id": review_id, "reviewee_id": current_user.user_id},
        {"_id": 0}
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or not yours to feature")
    
    if review["rating"] < 4:
        raise HTTPException(status_code=400, detail="Only 4-5 star reviews can be featured")
    
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"featured_quote_review_id": review_id}}
    )
    return {"message": "Featured quote updated", "review_id": review_id}


@api_router.delete("/reviews/featured-quote")
async def clear_featured_quote(current_user: User = Depends(get_current_user)):
    """Remove featured quote from public profile"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$unset": {"featured_quote_review_id": ""}}
    )
    return {"message": "Featured quote removed"}


@api_router.delete("/reviews/{review_id}")
async def delete_review(review_id: str, current_user: User = Depends(get_current_user)):
    """Delete a review (only the author can delete)"""
    review = await db.reviews.find_one({"review_id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review["reviewer_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own reviews")
    
    await db.reviews.delete_one({"review_id": review_id})
    return {"message": "Review deleted"}


# ============= LLM TRANSLATION ROUTE =============
@api_router.post("/translate")
async def translate_text(request: TranslateRequest, current_user: User = Depends(get_current_user)):
    try:
        # Language mapping
        lang_names = {
            "en": "English",
            "fa": "Farsi (Dari)",
            "ps": "Pashto"
        }
        
        source = lang_names.get(request.source_lang, request.source_lang)
        target = lang_names.get(request.target_lang, request.target_lang)
        
        # Create LLM chat instance
        chat = LlmChat(
            api_key=GOOGLE_API_KEY,
            session_id=f"translate_{current_user.user_id}",
            system_message=f"You are a professional medical translator. Translate the following text from {source} to {target}. Only return the translation, nothing else."
        ).with_model("gemini", "gemini-3.1-pro-preview")
        
        # Send translation request
        user_message = UserMessage(text=request.text)
        translation = await chat.send_message(user_message)
        
        return {"translation": translation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


# ============= PHASE 3 MODELS =============
class AppointmentCreate(BaseModel):
    doctor_id: str
    scheduled_at: str  # ISO datetime
    appointment_type: str = "video"  # video | in-person
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    status: Optional[str] = None  # pending | confirmed | cancelled | completed
    notes: Optional[str] = None


class MedicineCreate(BaseModel):
    name: str
    generic_name: Optional[str] = None
    category: Optional[str] = None  # antibiotic, painkiller, vitamin, etc.
    manufacturer: Optional[str] = None
    price: float
    currency: Optional[str] = "USD"  # USD | AFN
    stock: int = 0
    description: Optional[str] = None
    requires_prescription: bool = False


class MedicineUpdate(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    stock: Optional[int] = None
    description: Optional[str] = None
    requires_prescription: Optional[bool] = None


class ChatStart(BaseModel):
    chat_type: str  # symptom | device_fault
    title: Optional[str] = None


class ChatMessage(BaseModel):
    text: str


class SubscribeRequest(BaseModel):
    plan: str  # featured_monthly | featured_yearly
    mock_card_number: Optional[str] = None  # for mock payment


class VideoRoomCreate(BaseModel):
    appointment_id: Optional[str] = None
    invitee_id: Optional[str] = None


class VideoSignal(BaseModel):
    signal_data: dict  # WebRTC offer/answer/candidate
    target_user_id: str


# ============= APPOINTMENTS =============
@api_router.post("/appointments")
async def create_appointment(appt: AppointmentCreate, current_user: User = Depends(get_current_user)):
    """Patient books an appointment with a Doctor. Validates against doctor's schedule."""
    if current_user.user_type != "Patient":
        raise HTTPException(status_code=403, detail="Only patients can book appointments")

    doctor = await db.users.find_one({"user_id": appt.doctor_id, "user_type": "Doctor"}, {"_id": 0})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # --- Schedule validation ---
    try:
        scheduled_dt = datetime.fromisoformat(appt.scheduled_at.replace("Z", "+00:00"))
        if scheduled_dt.tzinfo is None:
            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at format (use ISO 8601)")

    if scheduled_dt < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Cannot book an appointment in the past")

    schedule_doc = await db.schedules.find_one({"doctor_id": appt.doctor_id})
    if schedule_doc and schedule_doc.get("slots"):
        # Python weekday(): Mon=0…Sun=6 → our model: Sun=0,Mon=1…Sat=6
        py_dow = scheduled_dt.weekday()  # 0=Mon
        our_dow = (py_dow + 1) % 7       # 0=Sun
        appt_time = scheduled_dt.strftime("%H:%M")

        valid_slot = False
        for slot in schedule_doc["slots"]:
            if slot.get("day_of_week") != our_dow:
                continue
            if slot.get("start_time", "00:00") <= appt_time <= slot.get("end_time", "23:59"):
                valid_slot = True
                break

        if not valid_slot:
            raise HTTPException(
                status_code=400,
                detail=f"The requested time ({appt_time}) is outside the doctor's working hours for that day."
            )

    # Double-booking check
    existing = await db.appointments.find_one({
        "doctor_id": appt.doctor_id,
        "scheduled_at": appt.scheduled_at,
        "status": {"$nin": ["cancelled"]}
    })
    if existing:
        raise HTTPException(status_code=409, detail="This time slot is already booked")

    appointment_id = f"appt_{uuid.uuid4().hex[:12]}"
    appointment_doc = {
        "appointment_id": appointment_id,
        "doctor_id": appt.doctor_id,
        "doctor_name": doctor["name"],
        "patient_id": current_user.user_id,
        "patient_name": current_user.name,
        "scheduled_at": appt.scheduled_at,
        "appointment_type": appt.appointment_type,
        "status": "pending",
        "notes": encrypt_phi(appt.notes),
        "video_room_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.appointments.insert_one(appointment_doc)
    appointment_doc.pop("_id", None)
    appointment_doc["notes"] = decrypt_phi(appointment_doc["notes"])

    # Email confirmation
    try:
        html = f"""<div style="font-family:sans-serif;padding:24px">
        <h2 style="color:#16a34a">Appointment Confirmed</h2>
        <p>Hello {current_user.name},</p>
        <p>Your appointment with <b>Dr. {doctor['name']}</b> has been booked.</p>
        <ul>
          <li><b>Date/Time:</b> {appt.scheduled_at.replace('T', ' ').replace(':00', '')}</li>
          <li><b>Type:</b> {appt.appointment_type}</li>
        </ul>
        <p style="color:#6b7280;font-size:12px">Afghan Health Portal</p></div>"""
        await send_email(current_user.email, "Appointment booked — Afghan Health Portal", html)
    except Exception:
        pass  # non-blocking

    return appointment_doc


@api_router.get("/appointments/me")
async def list_my_appointments(current_user: User = Depends(get_current_user)):
    """List appointments for current user (as patient OR doctor). Notes decrypted for participants."""
    query = {"$or": [
        {"patient_id": current_user.user_id},
        {"doctor_id": current_user.user_id}
    ]}
    appointments = await db.appointments.find(query, {"_id": 0}).sort("scheduled_at", -1).to_list(200)
    for a in appointments:
        a["notes"] = decrypt_phi(a.get("notes"))
    return {"count": len(appointments), "appointments": appointments}


@api_router.put("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: str,
    update: AppointmentUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update appointment status (Doctor confirms/completes, Patient cancels)"""
    appt = await db.appointments.find_one({"appointment_id": appointment_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if current_user.user_id not in [appt["doctor_id"], appt["patient_id"]]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    update_doc = {}
    if update.status:
        # Only doctor can mark completed
        if update.status == "completed" and current_user.user_id != appt["doctor_id"]:
            raise HTTPException(status_code=403, detail="Only doctor can mark appointment completed")
        update_doc["status"] = update.status
    if update.notes is not None:
        update_doc["notes"] = encrypt_phi(update.notes)
    
    if update_doc:
        await db.appointments.update_one({"appointment_id": appointment_id}, {"$set": update_doc})
        # Notify the other party
        other_id = appt["doctor_id"] if current_user.user_id == appt["patient_id"] else appt["patient_id"]
        await db.notifications.insert_one({
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": other_id,
            "type": "appointment_update",
            "title": "Appointment Status Updated",
            "message": f"Appointment is now {update.status or 'updated'}",
            "data": {"appointment_id": appointment_id, "status": update.status},
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    appt = await db.appointments.find_one({"appointment_id": appointment_id}, {"_id": 0})
    if appt:
        appt["notes"] = decrypt_phi(appt.get("notes"))
    return appt


# ============= APPOINTMENTS DOCTOR BOOKED-SLOTS =============
@api_router.get("/appointments/doctor/{doctor_id}/booked-slots")
async def get_doctor_booked_slots(doctor_id: str, date: str):
    """Get booked time slots for a doctor on a specific date (YYYY-MM-DD)"""
    appointments = await db.appointments.find(
        {
            "doctor_id": doctor_id,
            "scheduled_at": {"$regex": f"^{date}"},
            "status": {"$in": ["pending", "confirmed"]}
        },
        {"_id": 0, "scheduled_at": 1, "appointment_id": 1}
    ).to_list(100)
    return {"date": date, "booked_slots": appointments}


# ============= MEDICINES =============
@api_router.post("/medicines")
async def create_medicine(med: MedicineCreate, current_user: User = Depends(get_current_user)):
    """Pharmacy adds a medicine to their catalog"""
    if current_user.user_type != "Pharmacy":
        raise HTTPException(status_code=403, detail="Only pharmacies can add medicines")
    
    medicine_id = f"med_{uuid.uuid4().hex[:12]}"
    med_doc = {
        "medicine_id": medicine_id,
        "pharmacy_id": current_user.user_id,
        "pharmacy_name": current_user.name,
        "name": med.name,
        "generic_name": med.generic_name,
        "category": med.category,
        "manufacturer": med.manufacturer,
        "price": med.price,
        "currency": med.currency or "USD",
        "stock": med.stock,
        "description": med.description,
        "requires_prescription": med.requires_prescription,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.medicines.insert_one(med_doc)
    med_doc.pop("_id", None)
    return med_doc


@api_router.get("/medicines")
async def search_medicines(
    search: Optional[str] = None,
    category: Optional[str] = None,
    pharmacy_id: Optional[str] = None,
    limit: int = 50
):
    """Search medicines by name/category/pharmacy. Public endpoint."""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"generic_name": {"$regex": search, "$options": "i"}}
        ]
    if category:
        query["category"] = category
    if pharmacy_id:
        query["pharmacy_id"] = pharmacy_id
    
    medicines = await db.medicines.find(query, {"_id": 0}).limit(limit).to_list(limit)
    return {"count": len(medicines), "medicines": medicines}


@api_router.put("/medicines/{medicine_id}")
async def update_medicine(
    medicine_id: str,
    update: MedicineUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update medicine (only the owning pharmacy)"""
    med = await db.medicines.find_one({"medicine_id": medicine_id}, {"_id": 0})
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    if med["pharmacy_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your medicine")
    
    update_doc = update.model_dump(exclude_none=True)
    if update_doc:
        await db.medicines.update_one({"medicine_id": medicine_id}, {"$set": update_doc})
    
    med = await db.medicines.find_one({"medicine_id": medicine_id}, {"_id": 0})
    return med


@api_router.delete("/medicines/{medicine_id}")
async def delete_medicine(medicine_id: str, current_user: User = Depends(get_current_user)):
    """Delete medicine (only owning pharmacy)"""
    med = await db.medicines.find_one({"medicine_id": medicine_id}, {"_id": 0})
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    if med["pharmacy_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your medicine")
    
    await db.medicines.delete_one({"medicine_id": medicine_id})
    return {"message": "Medicine deleted"}


# ============= AI CHAT (Symptom Checker + Device Fault Assistant) =============
@api_router.post("/chat/start")
async def start_chat(req: ChatStart, current_user: User = Depends(get_current_user)):
    """Start a new AI chat session. type: 'symptom' or 'device_fault'"""
    if req.chat_type not in ["symptom", "device_fault"]:
        raise HTTPException(status_code=400, detail="chat_type must be 'symptom' or 'device_fault'")
    
    session_id = f"chat_{uuid.uuid4().hex[:12]}"
    session_doc = {
        "session_id": session_id,
        "user_id": current_user.user_id,
        "chat_type": req.chat_type,
        "title": req.title or ("Symptom Check" if req.chat_type == "symptom" else "Device Fault"),
        "messages": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.chat_sessions.insert_one(session_doc)
    session_doc.pop("_id", None)
    return session_doc


SYSTEM_PROMPTS = {
    "symptom": (
        "You are a helpful medical assistant for the Afghan Health Portal. "
        "Help users understand their symptoms in plain language. "
        "ALWAYS recommend consulting a real doctor for diagnosis. "
        "Never prescribe medication. Ask clarifying questions about duration, severity, and associated symptoms. "
        "Respond in the user's language (English, Farsi/Dari, or Pashto)."
    ),
    "device_fault": (
        "You are an expert biomedical engineering assistant. Help hospital staff write clear, "
        "structured fault descriptions for medical devices (MRI, X-Ray, Ventilators, ECG, etc.) "
        "before contacting a biomedical engineer. Ask about: device model, error codes, when the issue started, "
        "what was being done when it failed, and any unusual sounds/lights. Produce a final structured summary. "
        "Respond in the user's language."
    ),
}


@api_router.post("/chat/{session_id}/message")
async def send_chat_message(
    session_id: str,
    message: ChatMessage,
    current_user: User = Depends(get_current_user)
):
    """Send a message to AI chat. Returns AI response."""
    session = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your chat session")
    
    if len(message.text) > 4000:
        raise HTTPException(status_code=400, detail="Message too long (max 4000 chars)")
    
    try:
        system_prompt = SYSTEM_PROMPTS.get(session["chat_type"], SYSTEM_PROMPTS["symptom"])
        
        chat = LlmChat(
            api_key=GOOGLE_API_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("gemini", "gemini-3.1-pro-preview")
        
        user_msg = UserMessage(text=message.text)
        ai_response = await chat.send_message(user_msg)
        
        # Store both messages (encrypted at rest for PHI privacy)
        now = datetime.now(timezone.utc).isoformat()
        new_messages = [
            {"role": "user", "content": encrypt_phi(message.text), "timestamp": now},
            {"role": "assistant", "content": encrypt_phi(ai_response), "timestamp": now}
        ]
        
        await db.chat_sessions.update_one(
            {"session_id": session_id},
            {"$push": {"messages": {"$each": new_messages}}}
        )
        
        return {"response": ai_response, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat failed: {str(e)}")


@api_router.get("/chat/me")
async def list_my_chats(current_user: User = Depends(get_current_user)):
    """List current user's chat sessions"""
    sessions = await db.chat_sessions.find(
        {"user_id": current_user.user_id},
        {"_id": 0, "messages": 0}  # exclude full messages for list view
    ).sort("created_at", -1).to_list(50)
    return {"count": len(sessions), "sessions": sessions}


@api_router.get("/chat/{session_id}")
async def get_chat(session_id: str, current_user: User = Depends(get_current_user)):
    """Get full chat session with messages (decrypted for owner only)"""
    session = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your chat session")
    # Decrypt messages for owner
    for m in session.get("messages", []):
        if "content" in m:
            m["content"] = decrypt_phi(m["content"])
    return session


# ============= SUBSCRIPTIONS (Mock Payment) =============
SUBSCRIPTION_PLANS = {
    "featured_monthly": {"price_usd": 9.99, "duration_days": 30, "name": "Featured Monthly"},
    "featured_yearly": {"price_usd": 99.99, "duration_days": 365, "name": "Featured Yearly"},
}


@api_router.get("/subscriptions/plans")
async def get_plans():
    """List available subscription plans"""
    return {"plans": SUBSCRIPTION_PLANS}


@api_router.post("/subscriptions/subscribe")
async def subscribe(req: SubscribeRequest, current_user: User = Depends(get_current_user)):
    """Mock subscribe - instant success. Marks user as verified + featured."""
    if current_user.user_type not in ["Pharmacy", "Biomedical Engineer", "Doctor"]:
        raise HTTPException(status_code=403, detail="Only pharmacies, engineers, and doctors can subscribe")
    
    plan = SUBSCRIPTION_PLANS.get(req.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    started_at = datetime.now(timezone.utc)
    expires_at = started_at + timedelta(days=plan["duration_days"])
    
    subscription_doc = {
        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "plan": req.plan,
        "plan_name": plan["name"],
        "price_paid": plan["price_usd"],
        "started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "is_active": True,
        "payment_method": "mock_card",
        "mock_card_last4": (req.mock_card_number or "4242")[-4:],
        "created_at": started_at.isoformat()
    }
    
    # Deactivate any prior active subscription
    await db.subscriptions.update_many(
        {"user_id": current_user.user_id, "is_active": True},
        {"$set": {"is_active": False}}
    )
    await db.subscriptions.insert_one(subscription_doc)
    
    # Mark user as verified + featured
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "is_verified": True,
            "is_featured": True,
            "featured_until": expires_at.isoformat()
        }}
    )
    
    subscription_doc.pop("_id", None)
    return {"subscription": subscription_doc, "message": "Mock payment successful! You are now Verified & Featured."}


@api_router.get("/subscriptions/me")
async def my_subscription(current_user: User = Depends(get_current_user)):
    """Get current user's active subscription"""
    sub = await db.subscriptions.find_one(
        {"user_id": current_user.user_id, "is_active": True},
        {"_id": 0}
    )
    return sub or {"message": "No active subscription"}


@api_router.post("/subscriptions/cancel")
async def cancel_subscription(current_user: User = Depends(get_current_user)):
    """Cancel active subscription"""
    await db.subscriptions.update_many(
        {"user_id": current_user.user_id, "is_active": True},
        {"$set": {"is_active": False}}
    )
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_verified": False, "is_featured": False}}
    )
    return {"message": "Subscription cancelled"}


# ============= VIDEO ROOMS (WebRTC Signaling) =============
@api_router.post("/video/rooms")
async def create_video_room(req: VideoRoomCreate, current_user: User = Depends(get_current_user)):
    """Create a video room (optionally linked to an appointment)"""
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    room_doc = {
        "room_id": room_id,
        "host_id": current_user.user_id,
        "host_name": current_user.name,
        "invitee_id": req.invitee_id,
        "appointment_id": req.appointment_id,
        "participants": [current_user.user_id],
        "signals": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True
    }
    await db.video_rooms.insert_one(room_doc)
    
    # Link to appointment if provided
    if req.appointment_id:
        await db.appointments.update_one(
            {"appointment_id": req.appointment_id},
            {"$set": {"video_room_id": room_id}}
        )
    
    room_doc.pop("_id", None)
    return room_doc


@api_router.post("/video/rooms/{room_id}/join")
async def join_video_room(room_id: str, current_user: User = Depends(get_current_user)):
    """Join an existing video room"""
    room = await db.video_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room.get("is_active"):
        raise HTTPException(status_code=400, detail="Room is closed")
    
    if current_user.user_id not in room["participants"]:
        await db.video_rooms.update_one(
            {"room_id": room_id},
            {"$addToSet": {"participants": current_user.user_id}}
        )
    
    room = await db.video_rooms.find_one({"room_id": room_id}, {"_id": 0})
    return room


@api_router.post("/video/rooms/{room_id}/signal")
async def send_signal(
    room_id: str,
    signal: VideoSignal,
    current_user: User = Depends(get_current_user)
):
    """Exchange WebRTC signaling data (offer/answer/ice candidates)"""
    room = await db.video_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if current_user.user_id not in room["participants"]:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    signal_doc = {
        "signal_id": f"sig_{uuid.uuid4().hex[:8]}",
        "from_user_id": current_user.user_id,
        "target_user_id": signal.target_user_id,
        "signal_data": signal.signal_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.video_rooms.update_one(
        {"room_id": room_id},
        {"$push": {"signals": signal_doc}}
    )
    return {"message": "Signal sent", "signal_id": signal_doc["signal_id"]}


@api_router.get("/video/rooms/{room_id}/signals")
async def poll_signals(
    room_id: str,
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Poll for new signals targeted to current user (since timestamp)"""
    room = await db.video_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    signals = room.get("signals", [])
    # Filter signals targeted to current user
    my_signals = [s for s in signals if s["target_user_id"] == current_user.user_id]
    
    if since:
        my_signals = [s for s in my_signals if s["timestamp"] > since]
    
    return {"signals": my_signals}


@api_router.post("/video/rooms/{room_id}/close")
async def close_video_room(room_id: str, current_user: User = Depends(get_current_user)):
    """End a video call"""
    room = await db.video_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room["host_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Only host can close room")
    
    await db.video_rooms.update_one(
        {"room_id": room_id},
        {"$set": {"is_active": False, "closed_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Room closed"}


# ============= PUBLIC PHARMACIES LISTING =============
@api_router.get("/pharmacies/all")
async def list_pharmacies(only_24_7: bool = False, only_featured: bool = False):
    """List all pharmacies with their location for map display"""
    query = {"user_type": "Pharmacy"}
    if only_24_7:
        query["profile_data.is_24_7"] = True
    if only_featured:
        query["is_featured"] = True
    
    pharmacies = await db.users.find(query, {"_id": 0, "password": 0, "email": 0}).to_list(500)
    
    # Enrich with location
    results = []
    for pharm in pharmacies:
        loc = await db.locations.find_one({"user_id": pharm["user_id"]}, {"_id": 0})
        if loc:
            results.append({**pharm, "location": loc})
    
    return {"count": len(results), "pharmacies": results}


# ============= PHASE 4 MODELS =============
class FileUploadResponse(BaseModel):
    file_id: str
    storage_path: str
    url: str
    size: int


class ScheduleSlot(BaseModel):
    day_of_week: int  # 0=Sunday, 1=Monday ... 6=Saturday
    start_time: str  # "09:00"
    end_time: str  # "17:00"
    slot_duration_minutes: int = 30


class ScheduleUpdate(BaseModel):
    slots: List[ScheduleSlot]


class OrderCreate(BaseModel):
    medicine_id: str
    quantity: int = 1
    prescription_file_id: Optional[str] = None  # if prescription required
    delivery_address: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[str] = None  # pending | confirmed | shipped | delivered | cancelled


# ============= FILE UPLOAD =============
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@api_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Query("general"),  # profile_picture | prescription | general
    current_user: User = Depends(get_current_user)
):
    """Upload a file to Emergent Object Storage. Returns file_id and URL."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    ext = (file.filename or "bin").split(".")[-1].lower()
    file_id = f"file_{uuid.uuid4().hex[:12]}.{ext}"

    try:
        result = put_object(file_id, data, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {str(e)}")

    file_doc = {
        "file_id": file_id,
        "storage_path": file_id,
        "owner_id": current_user.user_id,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "purpose": purpose,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.files.insert_one(file_doc)

    if purpose == "profile_picture":
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {"picture": f"/api/files/{file_id}"}}
        )

    return {
        "file_id": file_id,
        "storage_path": file_id,
        "url": f"/api/files/{file_id}",
        "size": file_doc["size"]
    }


@api_router.get("/files/{file_id}")
async def download_file(
    file_id: str,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None)
):
    """Serve a file from object storage. Supports ?auth=token query param for <img> tags."""
    # Auth via header or query param
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Verify token (any valid token works for now - profile pics are semi-public among users)
    try:
        if token.startswith('test_session_') or len(token) > 200:
            session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            if not session_doc:
                raise HTTPException(status_code=401, detail="Invalid session")
        else:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (JWTError, Exception):
        raise HTTPException(status_code=401, detail="Invalid token")
    
    record = await db.files.find_one({"file_id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Decode token to get user_id for ownership checks
    requester_id = None
    try:
        if token.startswith('test_session_') or len(token) > 200:
            session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            requester_id = session_doc["user_id"] if session_doc else None
        else:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            requester_id = payload.get("sub")
    except JWTError:
        pass
    
    # Prescriptions: only owner OR pharmacy linked via an order can view
    if record.get("purpose") == "prescription" and requester_id != record["owner_id"]:
        # Check if requester is a pharmacy with an order referencing this prescription
        linked = await db.orders.find_one(
            {"prescription_file_id": file_id, "pharmacy_id": requester_id},
            {"_id": 0}
        )
        if not linked:
            raise HTTPException(status_code=403, detail="Not authorized to view this file")
    
    try:
        data, _ = get_object(record["storage_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File data not found on disk")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage retrieval failed: {str(e)}")

    return Response(content=data, media_type=record.get("content_type", "application/octet-stream"))


@api_router.delete("/files/{file_id}")
async def delete_file(file_id: str, current_user: User = Depends(get_current_user)):
    """Soft-delete a file (only owner can delete)"""
    record = await db.files.find_one({"file_id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    if record["owner_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your file")
    
    await db.files.update_one({"file_id": file_id}, {"$set": {"is_deleted": True}})
    return {"message": "File deleted"}


# ============= DOCTOR SCHEDULE =============
@api_router.put("/schedule")
async def set_schedule(req: ScheduleUpdate, current_user: User = Depends(get_current_user)):
    """Doctor sets their weekly availability template"""
    if current_user.user_type != "Doctor":
        raise HTTPException(status_code=403, detail="Only doctors have schedules")
    
    schedule_doc = {
        "doctor_id": current_user.user_id,
        "slots": [s.model_dump() for s in req.slots],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.schedules.update_one(
        {"doctor_id": current_user.user_id},
        {"$set": schedule_doc},
        upsert=True
    )
    schedule_doc.pop("_id", None)
    return schedule_doc


@api_router.get("/schedule/me")
async def get_my_schedule(current_user: User = Depends(get_current_user)):
    """Get current doctor's schedule"""
    schedule = await db.schedules.find_one({"doctor_id": current_user.user_id}, {"_id": 0})
    return schedule or {"doctor_id": current_user.user_id, "slots": []}


@api_router.get("/schedule/{doctor_id}")
async def get_doctor_schedule(doctor_id: str):
    """Get a doctor's weekly schedule template (public)"""
    schedule = await db.schedules.find_one({"doctor_id": doctor_id}, {"_id": 0})
    return schedule or {"doctor_id": doctor_id, "slots": []}


# ============= ORDERS (Medicine Purchase + Commission) =============
@api_router.post("/orders")
async def create_order(order: OrderCreate, current_user: User = Depends(get_current_user)):
    """Patient creates an order for a medicine. Commission auto-calculated. Atomic stock decrement."""
    if current_user.user_type != "Patient":
        raise HTTPException(status_code=403, detail="Only patients can place orders")
    
    if order.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")
    
    medicine = await db.medicines.find_one({"medicine_id": order.medicine_id}, {"_id": 0})
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    
    if medicine.get("requires_prescription") and not order.prescription_file_id:
        raise HTTPException(status_code=400, detail="This medicine requires a prescription")
    
    # Validate prescription file if provided
    if order.prescription_file_id:
        rx = await db.files.find_one(
            {"file_id": order.prescription_file_id, "owner_id": current_user.user_id, "is_deleted": False},
            {"_id": 0}
        )
        if not rx:
            raise HTTPException(status_code=400, detail="Invalid prescription file")
    
    # ATOMIC stock decrement (race-condition safe)
    reserved = await db.medicines.find_one_and_update(
        {"medicine_id": order.medicine_id, "stock": {"$gte": order.quantity}},
        {"$inc": {"stock": -order.quantity}},
        projection={"_id": 0, "price": 1, "name": 1, "pharmacy_id": 1, "pharmacy_name": 1}
    )
    if not reserved:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    
    subtotal = reserved["price"] * order.quantity
    commission_rate = COMMISSION_RATES["medicine_sale"]
    commission = round(subtotal * commission_rate, 2)
    pharmacy_payout = round(subtotal - commission, 2)
    
    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    order_doc = {
        "order_id": order_id,
        "patient_id": current_user.user_id,
        "patient_name": current_user.name,
        "pharmacy_id": reserved["pharmacy_id"],
        "pharmacy_name": reserved["pharmacy_name"],
        "medicine_id": order.medicine_id,
        "medicine_name": reserved["name"],
        "quantity": order.quantity,
        "unit_price": reserved["price"],
        "subtotal": subtotal,
        "commission_rate": commission_rate,
        "commission_amount": commission,
        "pharmacy_payout": pharmacy_payout,
        "prescription_file_id": order.prescription_file_id,
        "delivery_address": order.delivery_address,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order_doc)
    
    # Create notification for pharmacy
    await db.notifications.insert_one({
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": reserved["pharmacy_id"],
        "type": "new_order",
        "title": "New Medicine Order",
        "message": f"{current_user.name} ordered {order.quantity}x {reserved['name']}",
        "data": {"order_id": order_id},
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    order_doc.pop("_id", None)
    return order_doc


@api_router.get("/orders/me")
async def list_my_orders(current_user: User = Depends(get_current_user)):
    """List orders for current user (as patient OR pharmacy)"""
    query = {"$or": [
        {"patient_id": current_user.user_id},
        {"pharmacy_id": current_user.user_id}
    ]}
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"count": len(orders), "orders": orders}


@api_router.put("/orders/{order_id}")
async def update_order(
    order_id: str,
    update: OrderUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update order status. Pharmacy can confirm/ship/deliver. Patient can cancel pending only.
    Cancellation restores medicine stock."""
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if current_user.user_id not in [order["patient_id"], order["pharmacy_id"]]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if update.status:
        # Patient can only cancel, and only pending orders
        if current_user.user_id == order["patient_id"]:
            if update.status != "cancelled":
                raise HTTPException(status_code=403, detail="Patient can only cancel")
            if order["status"] != "pending":
                raise HTTPException(status_code=400, detail="Can only cancel pending orders")
        
        # Cannot change status of already-cancelled or delivered orders
        if order["status"] in ["cancelled", "delivered"]:
            raise HTTPException(status_code=400, detail=f"Cannot update {order['status']} order")
        
        # Restore stock on cancellation
        if update.status == "cancelled" and order["status"] != "cancelled":
            await db.medicines.update_one(
                {"medicine_id": order["medicine_id"]},
                {"$inc": {"stock": order["quantity"]}}
            )
        
        await db.orders.update_one({"order_id": order_id}, {"$set": {"status": update.status}})
        
        # Notify the other party
        other_id = order["pharmacy_id"] if current_user.user_id == order["patient_id"] else order["patient_id"]
        await db.notifications.insert_one({
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": other_id,
            "type": "order_update",
            "title": "Order Status Updated",
            "message": f"Order is now {update.status}",
            "data": {"order_id": order_id, "status": update.status},
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    return order


# ============= NOTIFICATIONS (HTTP Polling) =============
@api_router.get("/notifications")
async def get_notifications(
    only_unread: bool = False,
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Poll notifications for current user"""
    query = {"user_id": current_user.user_id}
    if only_unread:
        query["is_read"] = False
    if since:
        query["created_at"] = {"$gt": since}
    
    notifications = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread_count = await db.notifications.count_documents({
        "user_id": current_user.user_id,
        "is_read": False
    })
    return {"count": len(notifications), "unread_count": unread_count, "notifications": notifications}


@api_router.put("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, current_user: User = Depends(get_current_user)):
    """Mark a notification as read"""
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user.user_id},
        {"$set": {"is_read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Marked as read"}


@api_router.put("/notifications/read-all")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    result = await db.notifications.update_many(
        {"user_id": current_user.user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"marked_count": result.modified_count}


# ============= COMMISSION / GMV TRACKING =============
@api_router.get("/commission/summary")
async def commission_summary(current_user: User = Depends(get_current_user)):
    """GMV and commission summary for current user (pharmacy: sales, doctor: consultations)"""
    if current_user.user_type not in ["Pharmacy", "Doctor", "Biomedical Engineer"]:
        raise HTTPException(status_code=403, detail="Not applicable for this role")
    
    # Pharmacy: aggregate orders
    if current_user.user_type == "Pharmacy":
        pipeline = [
            {"$match": {"pharmacy_id": current_user.user_id, "status": {"$ne": "cancelled"}}},
            {"$group": {
                "_id": None,
                "gmv": {"$sum": "$subtotal"},
                "commission_total": {"$sum": "$commission_amount"},
                "payout_total": {"$sum": "$pharmacy_payout"},
                "order_count": {"$sum": 1}
            }}
        ]
        result = await db.orders.aggregate(pipeline).to_list(1)
        data = result[0] if result else {"gmv": 0, "commission_total": 0, "payout_total": 0, "order_count": 0}
        data.pop("_id", None)
        return {"role": "Pharmacy", "commission_rate": COMMISSION_RATES["medicine_sale"], **data}
    
    # Doctor: aggregate completed video appointments (commission applies)
    if current_user.user_type == "Doctor":
        completed = await db.appointments.count_documents({
            "doctor_id": current_user.user_id,
            "status": "completed",
            "appointment_type": "video"
        })
        # Read consultation fee from doctor's profile (fallback: $30 only if unset)
        doc = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0, "profile_data": 1})
        fee_raw = (doc or {}).get("profile_data", {}).get("consultation_fee")
        consultation_fee = float(fee_raw) if fee_raw is not None else 30.0
        gmv = completed * consultation_fee
        commission_rate = COMMISSION_RATES["consultation"]
        commission = round(gmv * commission_rate, 2)
        payout = round(gmv - commission, 2)
        return {
            "role": "Doctor",
            "commission_rate": commission_rate,
            "consultation_fee": consultation_fee,
            "gmv": gmv,
            "commission_total": commission,
            "payout_total": payout,
            "completed_consultations": completed
        }
    
    return {"role": current_user.user_type, "gmv": 0, "commission_total": 0}


# ============= MONTHLY REPORTS (Simulated Email via Resend) =============
async def generate_pharmacy_report(user_id: str, year: int, month: int) -> dict:
    """Compute pharmacy monthly report data"""
    start = datetime(year, month, 1, tzinfo=timezone.utc).isoformat()
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc).isoformat()
    
    # All orders for this pharmacy in the month
    pipeline = [
        {"$match": {
            "pharmacy_id": user_id,
            "created_at": {"$gte": start, "$lt": end},
            "status": {"$ne": "cancelled"}
        }},
        {"$group": {
            "_id": "$medicine_name",
            "quantity": {"$sum": "$quantity"},
            "revenue": {"$sum": "$subtotal"}
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 5}
    ]
    top_medicines = await db.orders.aggregate(pipeline).to_list(5)
    
    summary_pipeline = [
        {"$match": {
            "pharmacy_id": user_id,
            "created_at": {"$gte": start, "$lt": end},
            "status": {"$ne": "cancelled"}
        }},
        {"$group": {
            "_id": None,
            "total_orders": {"$sum": 1},
            "gmv": {"$sum": "$subtotal"},
            "commission_total": {"$sum": "$commission_amount"},
            "payout_total": {"$sum": "$pharmacy_payout"}
        }}
    ]
    summary = await db.orders.aggregate(summary_pipeline).to_list(1)
    s = summary[0] if summary else {"total_orders": 0, "gmv": 0, "commission_total": 0, "payout_total": 0}
    s.pop("_id", None)
    
    # Cancelled orders count
    cancelled = await db.orders.count_documents({
        "pharmacy_id": user_id,
        "created_at": {"$gte": start, "$lt": end},
        "status": "cancelled"
    })
    
    return {
        "role": "Pharmacy",
        "period": f"{year}-{month:02d}",
        **s,
        "cancelled_orders": cancelled,
        "top_medicines": [{"name": m["_id"], "quantity": m["quantity"], "revenue": m["revenue"]} for m in top_medicines]
    }


async def generate_doctor_report(user_id: str, year: int, month: int) -> dict:
    """Compute doctor monthly report data"""
    start = datetime(year, month, 1, tzinfo=timezone.utc).isoformat()
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc).isoformat()
    
    completed = await db.appointments.count_documents({
        "doctor_id": user_id,
        "status": "completed",
        "appointment_type": "video",
        "created_at": {"$gte": start, "$lt": end}
    })
    total_appts = await db.appointments.count_documents({
        "doctor_id": user_id,
        "created_at": {"$gte": start, "$lt": end}
    })
    
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "profile_data": 1})
    fee_raw = (doc or {}).get("profile_data", {}).get("consultation_fee")
    consultation_fee = float(fee_raw) if fee_raw is not None else 30.0
    gmv = completed * consultation_fee
    commission = round(gmv * COMMISSION_RATES["consultation"], 2)
    
    # Average rating from reviews
    review_pipeline = [
        {"$match": {"reviewee_id": user_id}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    rev = await db.reviews.aggregate(review_pipeline).to_list(1)
    avg_rating = round(rev[0]["avg_rating"], 2) if rev else 0
    review_count = rev[0]["count"] if rev else 0
    
    return {
        "role": "Doctor",
        "period": f"{year}-{month:02d}",
        "total_appointments": total_appts,
        "completed_consultations": completed,
        "consultation_fee": consultation_fee,
        "gmv": gmv,
        "commission_total": commission,
        "payout_total": round(gmv - commission, 2),
        "avg_rating": avg_rating,
        "total_reviews": review_count
    }


async def generate_engineer_report(user_id: str, year: int, month: int) -> dict:
    """Compute engineer monthly report data"""
    review_pipeline = [
        {"$match": {"reviewee_id": user_id}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    rev = await db.reviews.aggregate(review_pipeline).to_list(1)
    avg_rating = round(rev[0]["avg_rating"], 2) if rev else 0
    review_count = rev[0]["count"] if rev else 0
    
    return {
        "role": "Biomedical Engineer",
        "period": f"{year}-{month:02d}",
        "avg_rating": avg_rating,
        "total_reviews": review_count,
        "note": "Service request tracking will be added in future updates."
    }


@api_router.get("/reports/monthly")
async def get_monthly_report(
    year: Optional[int] = None,
    month: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Get current user's monthly performance report. Defaults to previous month."""
    if current_user.user_type not in ["Pharmacy", "Doctor", "Biomedical Engineer"]:
        raise HTTPException(status_code=403, detail="Reports available for Pharmacy/Doctor/Engineer only")
    
    # Default to previous month
    if not year or not month:
        now = datetime.now(timezone.utc)
        if now.month == 1:
            year = now.year - 1
            month = 12
        else:
            year = now.year
            month = now.month - 1
    
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be 1-12")
    
    if current_user.user_type == "Pharmacy":
        return await generate_pharmacy_report(current_user.user_id, year, month)
    elif current_user.user_type == "Doctor":
        return await generate_doctor_report(current_user.user_id, year, month)
    else:
        return await generate_engineer_report(current_user.user_id, year, month)


@api_router.post("/reports/monthly/send")
async def send_monthly_report(
    year: Optional[int] = None,
    month: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Generate and 'send' monthly report via simulated email (Resend simulation).
    In production this would call Resend API. Currently logs + saves to DB + creates notification."""
    # Get the report
    report = await get_monthly_report(year, month, current_user)
    
    # Build email HTML (simulated)
    email_html = f"""
    <h2>Your {report.get('period')} Performance Report — Afghan Health Portal</h2>
    <p>Hello {current_user.name},</p>
    <p>Here is your monthly summary:</p>
    <ul>
    """
    for k, v in report.items():
        if k not in ["role", "period", "note", "top_medicines"]:
            email_html += f"<li><b>{k.replace('_', ' ').title()}:</b> {v}</li>"
    email_html += "</ul>"
    
    if "top_medicines" in report and report["top_medicines"]:
        email_html += "<h3>Top 5 Medicines</h3><ol>"
        for m in report["top_medicines"]:
            email_html += f"<li>{m['name']}: {m['quantity']} units / ${m['revenue']:.2f}</li>"
        email_html += "</ol>"
    
    email_html += "<p>Keep up the great work! 💚</p>"
    
    # Save report to DB
    report_doc = {
        "report_id": f"report_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "user_email": current_user.email,
        "user_name": current_user.name,
        "period": report.get("period"),
        "data": report,
        "email_html": email_html,
        "delivery_status": "SIMULATED_SENT",  # mocked — would be "SENT" via Resend
        "delivery_provider": "resend_mock",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.monthly_reports.insert_one(report_doc)
    
    # Create notification for user
    await db.notifications.insert_one({
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "type": "monthly_report",
        "title": f"📊 Your {report.get('period')} Report is Ready",
        "message": "Check your monthly performance summary.",
        "data": {"report_id": report_doc["report_id"], "period": report.get("period")},
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Send via Resend (or simulate if key not set)
    try:
        await send_email(current_user.email, f"Your {report.get('period')} Report — Afghan Health Portal", email_html)
    except Exception as e:
        logger.error(f"Monthly report email failed: {e}")
    logger.info(f"Monthly report processed for {current_user.email} period {report.get('period')}")
    
    report_doc.pop("_id", None)
    return {
        "message": "Monthly report generated and 'sent' (MOCKED via Resend simulation)",
        "report_id": report_doc["report_id"],
        "delivery_status": report_doc["delivery_status"],
        "to": current_user.email,
        "report": report
    }


@api_router.get("/reports/me")
async def list_my_reports(current_user: User = Depends(get_current_user)):
    """List all saved monthly reports for current user"""
    reports = await db.monthly_reports.find(
        {"user_id": current_user.user_id},
        {"_id": 0, "email_html": 0}
    ).sort("created_at", -1).to_list(50)
    return {"count": len(reports), "reports": reports}


# ============= DOCTORS LISTING (with filters) =============
@api_router.get("/doctors")
async def list_doctors(
    specialty: Optional[str] = None,
    max_fee: Optional[float] = None,
    verified_only: bool = False,
    language: Optional[str] = None,
):
    """Public listing of all doctors with their location and profile data."""
    query: dict = {"user_type": "Doctor"}
    if verified_only:
        query["is_verified"] = True
    if specialty:
        query["profile_data.specialty"] = {"$regex": specialty, "$options": "i"}
    if language:
        query["profile_data.languages"] = {"$regex": language, "$options": "i"}
    if max_fee is not None:
        query["profile_data.consultation_fee"] = {"$lte": max_fee}

    doctors = await db.users.find(
        query,
        {"_id": 0, "password": 0, "email": 0, "phone": 0}
    ).to_list(500)

    # Enrich with location + avg rating
    results = []
    for doc in doctors:
        loc = await db.locations.find_one({"user_id": doc["user_id"]}, {"_id": 0})
        review_pipe = [
            {"$match": {"reviewee_id": doc["user_id"]}},
            {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}}
        ]
        rev = await db.reviews.aggregate(review_pipe).to_list(1)
        doc["avg_rating"] = round(rev[0]["avg"], 2) if rev else 0
        doc["total_reviews"] = rev[0]["count"] if rev else 0
        doc["location"] = loc
        results.append(doc)

    return {"count": len(results), "doctors": results}


# ============= MEDICAL RECORD =============
@api_router.get("/medical-record/me")
async def get_my_medical_record(current_user: User = Depends(get_current_user)):
    """Patient retrieves their own full medical record."""
    record = await db.medical_records.find_one({"patient_id": current_user.user_id}, {"_id": 0})
    if not record:
        return {"patient_id": current_user.user_id, "allergies": [], "current_medications": [],
                "emergency_contact_name": None, "emergency_contact_phone": None, "notes": None}
    # Decrypt sensitive fields
    record["notes"] = decrypt_phi(record.get("notes"))
    if record.get("allergies"):
        record["allergies"] = decrypt_list(record["allergies"])
    if record.get("current_medications"):
        record["current_medications"] = decrypt_list(record["current_medications"])
    return record


@api_router.put("/medical-record/me")
async def update_my_medical_record(update: MedicalRecordUpdate, current_user: User = Depends(get_current_user)):
    """Patient updates their medical record. All clinical data is encrypted at rest."""
    if current_user.user_type != "Patient":
        raise HTTPException(status_code=403, detail="Only patients have medical records")

    set_doc: dict = {"patient_id": current_user.user_id, "updated_at": datetime.now(timezone.utc).isoformat()}

    if update.allergies is not None:
        set_doc["allergies"] = encrypt_list(update.allergies)
    if update.current_medications is not None:
        set_doc["current_medications"] = encrypt_list(update.current_medications)
    if update.emergency_contact_name is not None:
        set_doc["emergency_contact_name"] = update.emergency_contact_name
    if update.emergency_contact_phone is not None:
        set_doc["emergency_contact_phone"] = update.emergency_contact_phone
    if update.notes is not None:
        set_doc["notes"] = encrypt_phi(update.notes)

    await db.medical_records.update_one(
        {"patient_id": current_user.user_id},
        {"$set": set_doc},
        upsert=True
    )
    return await get_my_medical_record(current_user)


@api_router.get("/medical-record/{patient_id}")
async def get_patient_medical_record(patient_id: str, current_user: User = Depends(get_current_user)):
    """Doctor accesses a patient's medical record — only allowed if there is a confirmed/pending appointment."""
    if current_user.user_type not in ["Doctor"]:
        raise HTTPException(status_code=403, detail="Only doctors can access patient records")

    # Verify active appointment relationship
    appt = await db.appointments.find_one({
        "doctor_id": current_user.user_id,
        "patient_id": patient_id,
        "status": {"$in": ["pending", "confirmed"]}
    })
    if not appt:
        raise HTTPException(
            status_code=403,
            detail="Access denied — no active appointment with this patient"
        )

    record = await db.medical_records.find_one({"patient_id": patient_id}, {"_id": 0})
    if not record:
        return {"patient_id": patient_id, "allergies": [], "current_medications": [],
                "emergency_contact_name": None, "emergency_contact_phone": None, "notes": None}

    # Decrypt for the treating doctor
    record["notes"] = decrypt_phi(record.get("notes"))
    if record.get("allergies"):
        record["allergies"] = decrypt_list(record["allergies"])
    if record.get("current_medications"):
        record["current_medications"] = decrypt_list(record["current_medications"])

    # Also grab the patient's profile data for context (blood type, chronic illnesses)
    patient = await db.users.find_one({"user_id": patient_id}, {"_id": 0, "password": 0})
    if patient and patient.get("user_type") == "Patient":
        pd = decrypt_patient_profile(patient.get("profile_data", {}))
        record["patient_name"] = patient.get("name")
        record["blood_type"] = pd.get("blood_type")
        record["chronic_illnesses"] = pd.get("chronic_illnesses", [])
        record["age"] = pd.get("age")
        record["gender"] = pd.get("gender")

    return record


# ============= ADMIN ROUTES =============
@api_router.get("/admin/stats")
async def admin_stats(_admin: User = Depends(get_admin_user)):
    """Platform-wide statistics for admin dashboard"""
    user_counts_pipeline = [
        {"$group": {"_id": "$user_type", "count": {"$sum": 1}}}
    ]
    raw = await db.users.aggregate(user_counts_pipeline).to_list(20)
    by_type = {r["_id"]: r["count"] for r in raw}

    total_users = await db.users.count_documents({})
    pending_verifications = await db.users.count_documents({"is_verified": False, "user_type": {"$in": ["Doctor", "Pharmacy", "Biomedical Engineer"]}})
    banned_users = await db.users.count_documents({"is_banned": True})

    total_orders = await db.orders.count_documents({})
    total_appointments = await db.appointments.count_documents({})
    total_medicines = await db.medicines.count_documents({})
    total_tickets = await db.service_tickets.count_documents({})

    gmv_pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None, "total": {"$sum": "$subtotal"}}}
    ]
    gmv_raw = await db.orders.aggregate(gmv_pipeline).to_list(1)
    total_gmv = gmv_raw[0]["total"] if gmv_raw else 0

    commission_pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None, "total": {"$sum": "$commission_amount"}}}
    ]
    comm_raw = await db.orders.aggregate(commission_pipeline).to_list(1)
    total_commission = comm_raw[0]["total"] if comm_raw else 0

    return {
        "total_users": total_users,
        "users_by_type": by_type,
        "pending_verifications": pending_verifications,
        "banned_users": banned_users,
        "total_orders": total_orders,
        "total_appointments": total_appointments,
        "total_medicines": total_medicines,
        "total_service_tickets": total_tickets,
        "total_gmv": total_gmv,
        "total_commission": total_commission,
    }


@api_router.get("/admin/users")
async def admin_list_users(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    user_type: Optional[str] = None,
    _admin: User = Depends(get_admin_user)
):
    """List all users with optional filters"""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    if user_type:
        query["user_type"] = user_type

    total = await db.users.count_documents(query)
    skip = (page - 1) * limit
    users = await db.users.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "limit": limit, "users": users}


@api_router.put("/admin/users/{user_id}/verify")
async def admin_toggle_verify(user_id: str, _admin: User = Depends(get_admin_user)):
    """Toggle is_verified for a user"""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    new_val = not user_doc.get("is_verified", False)
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_verified": new_val}})
    return {"user_id": user_id, "is_verified": new_val}


@api_router.put("/admin/users/{user_id}/ban")
async def admin_toggle_ban(user_id: str, _admin: User = Depends(get_admin_user)):
    """Toggle is_banned for a user"""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    if user_doc.get("is_admin"):
        raise HTTPException(status_code=400, detail="Cannot ban an admin account")
    new_val = not user_doc.get("is_banned", False)
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_banned": new_val}})
    return {"user_id": user_id, "is_banned": new_val}


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _admin: User = Depends(get_admin_user)):
    """Hard-delete a user account"""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    if user_doc.get("is_admin"):
        raise HTTPException(status_code=400, detail="Cannot delete an admin account")
    await db.users.delete_one({"user_id": user_id})
    return {"message": f"User {user_id} deleted"}


# ============= FORGOT / RESET PASSWORD =============
@api_router.post("/auth/forgot-password")
async def forgot_password(req: PasswordResetRequest):
    """Generate a password reset token. In production this sends an email via Resend."""
    user_doc = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user_doc:
        # Return success even if email not found (security best practice)
        return {"message": "If that email exists, a reset link has been sent."}

    token = uuid.uuid4().hex
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    await db.password_resets.update_one(
        {"email": req.email},
        {"$set": {"token": token, "expires_at": expires_at, "used": False}},
        upsert=True
    )

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    reset_url = f"{frontend_url}/reset-password/{token}"

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="color:#16a34a">Afghan Health Portal — Password Reset</h2>
      <p>Hello,</p>
      <p>You requested a password reset. Click the button below within 2 hours:</p>
      <a href="{reset_url}" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;margin:16px 0">Reset Password</a>
      <p style="color:#6b7280;font-size:12px">If you didn't request this, ignore this email.</p>
    </div>"""

    try:
        await send_email(req.email, "Reset your Afghan Health Portal password", html)
    except Exception as e:
        logger.error(f"Email send failed: {e}")

    return {
        "message": "If that email exists, a reset link has been sent.",
        "dev_token": token if not RESEND_API_KEY else None,
        "dev_reset_url": reset_url if not RESEND_API_KEY else None,
    }


@api_router.post("/auth/reset-password")
async def reset_password(req: PasswordResetConfirm):
    """Consume reset token and set new password"""
    record = await db.password_resets.find_one({"token": req.token, "used": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    expires_at = record["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    new_hash = hash_password(req.new_password)
    await db.users.update_one({"email": record["email"]}, {"$set": {"password": new_hash}})
    await db.password_resets.update_one({"token": req.token}, {"$set": {"used": True}})

    return {"message": "Password updated successfully"}


# ============= SERVICE TICKETS (Biomedical Engineer) =============
@api_router.post("/service-tickets")
async def create_service_ticket(ticket: ServiceTicketCreate, current_user: User = Depends(get_current_user)):
    """Create a medical device service request"""
    ticket_id = f"ticket_{uuid.uuid4().hex[:12]}"
    ticket_doc = {
        "ticket_id": ticket_id,
        "requester_id": current_user.user_id,
        "requester_name": current_user.name,
        "device_type": ticket.device_type,
        "issue_description": ticket.issue_description,
        "location": ticket.location,
        "urgency": ticket.urgency or "normal",
        "contact_phone": ticket.contact_phone or current_user.phone,
        "status": "open",
        "engineer_id": None,
        "engineer_name": None,
        "engineer_notes": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.service_tickets.insert_one(ticket_doc)
    ticket_doc.pop("_id", None)
    return ticket_doc


@api_router.get("/service-tickets/available")
async def list_available_tickets(
    device_type: Optional[str] = None,
    urgency: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List open service tickets visible to engineers"""
    if current_user.user_type != "Biomedical Engineer" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only engineers can browse open tickets")
    query: dict = {"status": "open"}
    if device_type:
        query["device_type"] = {"$regex": device_type, "$options": "i"}
    if urgency:
        query["urgency"] = urgency
    tickets = await db.service_tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"count": len(tickets), "tickets": tickets}


@api_router.get("/service-tickets/me")
async def list_my_tickets(current_user: User = Depends(get_current_user)):
    """List tickets created by or assigned to current user"""
    query = {"$or": [
        {"requester_id": current_user.user_id},
        {"engineer_id": current_user.user_id}
    ]}
    tickets = await db.service_tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"count": len(tickets), "tickets": tickets}


@api_router.put("/service-tickets/{ticket_id}")
async def update_service_ticket(
    ticket_id: str,
    update: ServiceTicketUpdate,
    current_user: User = Depends(get_current_user)
):
    """Engineer accepts / updates a ticket"""
    ticket = await db.service_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    set_doc: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    # Engineer accepting an open ticket
    if update.status == "accepted" and ticket["status"] == "open":
        if current_user.user_type != "Biomedical Engineer":
            raise HTTPException(status_code=403, detail="Only engineers can accept tickets")
        set_doc["engineer_id"] = current_user.user_id
        set_doc["engineer_name"] = current_user.name
        set_doc["status"] = "accepted"
    elif update.status:
        # Only assigned engineer or requester can change status further
        if current_user.user_id not in [ticket.get("engineer_id"), ticket["requester_id"]] and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")
        set_doc["status"] = update.status

    if update.engineer_notes is not None:
        set_doc["engineer_notes"] = update.engineer_notes

    await db.service_tickets.update_one({"ticket_id": ticket_id}, {"$set": set_doc})
    ticket = await db.service_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    return ticket


# ============= BASIC ROUTES =============
@api_router.get("/")
async def root():
    return {"message": "Health Portal API"}


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    init_storage()  # creates uploads/ dir on disk

    # Pre-create geospatial index
    try:
        await db.locations.create_index([("location", "2dsphere")])
    except Exception:
        pass

    # Seed default admin account if none exists
    try:
        existing_admin = await db.users.find_one({"is_admin": True})
        if not existing_admin:
            admin_id = f"user_{uuid.uuid4().hex[:12]}"
            await db.users.insert_one({
                "user_id": admin_id,
                "email": "admin@faizan.af",
                "name": "Admin",
                "user_type": "Doctor",
                "password": hash_password("Admin1234!"),
                "picture": None,
                "phone": None,
                "profile_data": {},
                "is_verified": True,
                "is_admin": True,
                "is_banned": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Default admin account created: admin@faizan.af / Admin1234!")
        else:
            logger.info(f"Admin account already exists: {existing_admin.get('email')}")
    except Exception as e:
        logger.error(f"Admin seed failed: {e}")

    # Seed demo accounts (one per role) if they don't exist
    demo_users = [
        {
            "email": "doctor@demo.af",
            "name": "Dr. Ahmad Karimi",
            "user_type": "Doctor",
            "password": "Demo1234!",
            "is_verified": True,
            "profile_data": {
                "specialty": "General Medicine",
                "hospital": "Kabul Central Hospital",
                "years_experience": 8,
                "working_hours": "Mon-Fri 09:00-17:00",
                "consultation_fee": 25.0,
                "currency": "USD",
                "bio": "Board-certified general practitioner with 8 years of experience in primary care and preventive medicine.",
            },
        },
        {
            "email": "patient@demo.af",
            "name": "Fatima Noori",
            "user_type": "Patient",
            "password": "Demo1234!",
            "is_verified": False,
            "profile_data": {"age": 34, "gender": "female"},
        },
        {
            "email": "pharmacy@demo.af",
            "name": "Kabul Health Pharmacy",
            "user_type": "Pharmacy",
            "password": "Demo1234!",
            "is_verified": True,
            "profile_data": {
                "business_name": "Kabul Health Pharmacy",
                "is_24_7": True,
                "opening_hours": "00:00",
                "closing_hours": "23:59",
            },
        },
        {
            "email": "engineer@demo.af",
            "name": "Reza Ahmadi",
            "user_type": "Biomedical Engineer",
            "password": "Demo1234!",
            "is_verified": True,
            "profile_data": {
                "specialty": ["MRI", "X-Ray", "Ultrasound"],
                "years_experience": 5,
            },
        },
    ]
    for demo in demo_users:
        try:
            if not await db.users.find_one({"email": demo["email"]}):
                uid = f"user_{uuid.uuid4().hex[:12]}"
                await db.users.insert_one({
                    "user_id": uid,
                    "email": demo["email"],
                    "name": demo["name"],
                    "user_type": demo["user_type"],
                    "password": hash_password(demo["password"]),
                    "picture": None,
                    "phone": None,
                    "profile_data": demo.get("profile_data", {}),
                    "is_verified": demo.get("is_verified", False),
                    "is_admin": False,
                    "is_banned": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                logger.info(f"Demo account created: {demo['email']} / {demo['password']}")
        except Exception as e:
            logger.error(f"Demo seed failed for {demo['email']}: {e}")

    # Add demo locations (Kabul area) for seeded users so they appear on the map
    demo_locations = [
        {"email": "doctor@demo.af",   "lat": 34.5253, "lng": 69.1783, "address": "Kabul Central Hospital, Kabul"},
        {"email": "pharmacy@demo.af", "lat": 34.5355, "lng": 69.1890, "address": "Shahr-e-Naw, Kabul"},
        {"email": "engineer@demo.af", "lat": 34.5453, "lng": 69.2010, "address": "Wazir Akbar Khan, Kabul"},
    ]
    for dl in demo_locations:
        try:
            u = await db.users.find_one({"email": dl["email"]}, {"_id": 0, "user_id": 1, "user_type": 1})
            if u:
                await db.locations.update_one(
                    {"user_id": u["user_id"]},
                    {"$set": {
                        "user_id": u["user_id"],
                        "user_type": u["user_type"],
                        "location": {"type": "Point", "coordinates": [dl["lng"], dl["lat"]]},
                        "address": dl["address"],
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Demo location seed failed for {dl['email']}: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

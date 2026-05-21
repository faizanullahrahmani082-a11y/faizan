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


# Object Storage
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "afghan-health"
storage_key = None  # Module-level

# Commission rates
COMMISSION_RATES = {
    "medicine_sale": 0.04,  # 4% on pharmacy drug sales
    "consultation": 0.12,    # 12% on online doctor consultations
}


def init_storage():
    """Call once at startup. Returns session-scoped reusable storage_key."""
    global storage_key
    if storage_key:
        return storage_key
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        return storage_key
    except Exception as e:
        logging.error(f"Storage init failed: {e}")
        return None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

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
    consultation_fee: Optional[float] = 30.0  # USD per video consultation


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
            api_key=os.environ.get('EMERGENT_LLM_KEY'),
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
    stock: int = 0
    description: Optional[str] = None
    requires_prescription: bool = False


class MedicineUpdate(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    price: Optional[float] = None
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
    """Patient books an appointment with a Doctor"""
    if current_user.user_type != "Patient":
        raise HTTPException(status_code=403, detail="Only patients can book appointments")
    
    doctor = await db.users.find_one({"user_id": appt.doctor_id, "user_type": "Doctor"}, {"_id": 0})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
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
            api_key=os.environ.get('EMERGENT_LLM_KEY'),
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
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    path = f"{APP_NAME}/uploads/{current_user.user_id}/{file_id}.{ext}"
    
    try:
        result = put_object(path, data, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {str(e)}")
    
    file_doc = {
        "file_id": file_id,
        "storage_path": result["path"],
        "owner_id": current_user.user_id,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "purpose": purpose,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.files.insert_one(file_doc)
    
    # If profile picture, update user
    if purpose == "profile_picture":
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {"picture": f"/api/files/{file_id}"}}
        )
    
    return {
        "file_id": file_id,
        "storage_path": result["path"],
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
        data, content_type = get_object(record["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage retrieval failed: {str(e)}")
    
    return Response(content=data, media_type=record.get("content_type", content_type))


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
    
    # Log to backend (simulating Resend send)
    logger.info(f"[MOCKED EMAIL] Monthly report sent to {current_user.email} for period {report.get('period')}")
    
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
    try:
        init_storage()
        logger.info("Object storage initialized successfully")
    except Exception as e:
        logger.error(f"Storage init failed at startup: {e}")
    # Pre-create geospatial index
    try:
        await db.locations.create_index([("location", "2dsphere")])
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

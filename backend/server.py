from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
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
from emergentintegrations.llm.chat import LlmChat, UserMessage

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
    user_type: str  # Doctor, Patient, Pharmacist, Biomedical Engineer
    picture: Optional[str] = None
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user_doc)
    
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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

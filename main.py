import os
import secrets
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, ForeignKey, Boolean, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-romantic-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite:///./love_app.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://love-web-mocha.vercel.app")
ALLOWED_ORIGINS = [FRONTEND_URL, "http://localhost:5500", "http://127.0.0.1:5500"]

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- SQL DB Models ---
class UserDB(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False, nullable=False)

class CardDB(Base):
    __tablename__ = "cards"
    id = Column(String, primary_key=True, index=True)
    type = Column(String)  # 'card' or 'proposal'
    sender_name = Column(String)
    partner_name = Column(String)
    message = Column(Text)
    proposal_question = Column(Text, nullable=True)
    theme = Column(String)
    bg_style = Column(String)
    card_container_style = Column(String)
    special_date = Column(String, nullable=True)
    image_data = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)

Base.metadata.create_all(bind=engine)

if "is_admin" not in {column["name"] for column in inspect(engine).get_columns("users")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))

# --- Schemas ---
class UserRegister(BaseModel):
    username: str
    password: str

class PasswordChange(BaseModel):
    password: str

class UserAdminResponse(BaseModel):
    id: str
    username: str
    is_admin: bool

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    is_admin: bool
    id: str

class CardCreate(BaseModel):
    type: str = "card"
    sender_name: str
    partner_name: str
    message: str
    proposal_question: Optional[str] = "Will You Marry Me? 💖"
    theme: str = "classic"
    bg_style: str = "dark"
    card_container_style: str = "velvet"
    special_date: Optional[str] = ""
    image_data: Optional[str] = ""

class CardResponse(CardCreate):
    id: str

# --- App Initialization ---
app = FastAPI(title="Love & Proposal Webpage API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Auth Helpers ---
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
    except JWTError as error:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from error
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user

def require_admin(user: UserDB = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user

def ensure_default_admin():
    db = SessionLocal()
    try:
        admin = db.query(UserDB).filter(UserDB.username == "admin").first()
        if not admin:
            db.add(UserDB(
                id=secrets.token_hex(8),
                username="admin",
                hashed_password=get_password_hash("pass"),
                is_admin=True,
            ))
            db.commit()
        elif not admin.is_admin:
            admin.is_admin = True
            db.commit()
    finally:
        db.close()

ensure_default_admin()

# --- API Endpoints ---
@app.get("/")
def home():
    return {"status": "Love Webpage Backend Active 💖"}

@app.post("/api/register", response_model=Token)
def register(user: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(UserDB).filter(UserDB.username == user.username.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    user_id = secrets.token_hex(8)
    db_user = UserDB(
        id=user_id,
        username=user.username.strip().lower(),
        hashed_password=get_password_hash(user.password)
    )
    db.add(db_user)
    db.commit()
    
    access_token = create_access_token(data={"sub": db_user.username, "id": user_id})
    return {"access_token": access_token, "token_type": "bearer", "username": db_user.username, "is_admin": False, "id": db_user.id}

@app.post("/api/login", response_model=Token)
def login(user: UserRegister, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.username == user.username.strip().lower()).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": db_user.username, "id": db_user.id})
    return {"access_token": access_token, "token_type": "bearer", "username": db_user.username, "is_admin": db_user.is_admin, "id": db_user.id}

@app.get("/api/admin/users", response_model=list[UserAdminResponse])
def list_users(_: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(UserDB).order_by(UserDB.username).all()

@app.patch("/api/admin/users/{user_id}/password")
def change_user_password(
    user_id: str,
    password: PasswordChange,
    _: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if len(password.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = get_password_hash(password.password)
    db.commit()
    return {"message": "Password updated"}

@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: str, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own admin account")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

@app.post("/api/cards", response_model=CardResponse)
def create_card(card: CardCreate, db: Session = Depends(get_db)):
    card_id = secrets.token_urlsafe(10)
    db_card = CardDB(
        id=card_id,
        type=card.type,
        sender_name=card.sender_name,
        partner_name=card.partner_name,
        message=card.message,
        proposal_question=card.proposal_question,
        theme=card.theme,
        bg_style=card.bg_style,
        card_container_style=card.card_container_style,
        special_date=card.special_date,
        image_data=card.image_data
    )
    db.add(db_card)
    db.commit()
    db.refresh(db_card)
    return db_card

@app.get("/api/cards/{card_id}", response_model=CardResponse)
def get_card(card_id: str, db: Session = Depends(get_db)):
    db_card = db.query(CardDB).filter(CardDB.id == card_id).first()
    if not db_card:
        raise HTTPException(status_code=404, detail="Love message not found!")
    return db_card
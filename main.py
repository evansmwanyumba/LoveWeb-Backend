import os
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


FRONTEND_URL = os.getenv("FRONTEND_URL", "https://love-web-mocha.vercel.app")
ALLOWED_ORIGINS = [FRONTEND_URL, "http://localhost:5500", "http://127.0.0.1:5500"]

app = FastAPI(title="Love & Proposal Webpage API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


cards: dict[str, CardResponse] = {}


@app.get("/")
def home():
    return {"status": "Love Webpage Backend Active", "storage": "in-memory"}


@app.post("/api/cards", response_model=CardResponse)
def create_card(card: CardCreate):
    card_id = secrets.token_urlsafe(10)
    saved_card = CardResponse(id=card_id, **card.model_dump())
    cards[card_id] = saved_card
    return saved_card


@app.get("/api/cards/{card_id}", response_model=CardResponse)
def get_card(card_id: str):
    card = cards.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Love message not found!")
    return card

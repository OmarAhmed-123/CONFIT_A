"""Mood-board CRUD — Group 1 §28.

Replaces the previous dead `user_style_profiles.moodboard_urls` column
with a proper owned table (mood_boards + mood_board_items). Every route
requires authentication and enforces ownership via profile_id → user_id
lookup — cross-user access is not possible.
"""
import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationDomainError,
)
from backend.app.models.profile import MoodBoard, MoodBoardItem, UserStyleProfile
from backend.app.models.user import User

router = APIRouter(prefix="/me/mood-boards", tags=["Mood Boards (G1)"])


class MoodBoardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class MoodBoardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class MoodBoardItemCreate(BaseModel):
    kind: str = Field(pattern="^(url|product|upload)$")
    payload: dict = Field(default_factory=dict)


class MoodBoardItemOut(BaseModel):
    id: int
    kind: str
    payload: dict
    position: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MoodBoardOut(BaseModel):
    id: int
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    items: List[MoodBoardItemOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


def _ensure_profile(db: Session, user: User) -> UserStyleProfile:
    profile = db.query(UserStyleProfile).filter(UserStyleProfile.user_id == user.id).first()
    if not profile:
        # Create a stub profile so the board FK is valid — this is an
        # explicit user action (POST /me/mood-boards), not a fabricated
        # side effect on read.
        profile = UserStyleProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _ensure_ownership(db: Session, user: User, board_id: int) -> MoodBoard:
    board = db.query(MoodBoard).filter(MoodBoard.id == board_id).first()
    if not board:
        raise ResourceNotFoundError("MoodBoard", board_id)
    profile = db.query(UserStyleProfile).filter(UserStyleProfile.id == board.profile_id).first()
    if not profile or profile.user_id != user.id:
        raise AuthorizationError("Mood board does not belong to the authenticated user.")
    return board


def _serialize(board: MoodBoard) -> dict:
    return {
        "id": board.id,
        "title": board.title,
        "description": board.description,
        "created_at": board.created_at,
        "updated_at": board.updated_at,
        "items": [
            {
                "id": it.id,
                "kind": it.kind,
                "payload": json.loads(it.payload_json or "{}"),
                "position": it.position,
                "created_at": it.created_at,
            }
            for it in sorted(board.items, key=lambda x: x.position)
        ],
    }


@router.get("", response_model=List[MoodBoardOut])
def list_boards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(UserStyleProfile).filter(UserStyleProfile.user_id == user.id).first()
    if not profile:
        return []
    boards = db.query(MoodBoard).filter(MoodBoard.profile_id == profile.id).order_by(MoodBoard.created_at).all()
    return [_serialize(b) for b in boards]


@router.post("", response_model=MoodBoardOut, status_code=201)
def create_board(payload: MoodBoardCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = _ensure_profile(db, user)
    board = MoodBoard(profile_id=profile.id, title=payload.title, description=payload.description)
    db.add(board)
    db.commit()
    db.refresh(board)
    return _serialize(board)


@router.get("/{board_id}", response_model=MoodBoardOut)
def get_board(board_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize(_ensure_ownership(db, user, board_id))


@router.patch("/{board_id}", response_model=MoodBoardOut)
def rename_board(board_id: int, payload: MoodBoardUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _ensure_ownership(db, user, board_id)
    if payload.title is not None:
        board.title = payload.title
    if payload.description is not None:
        board.description = payload.description
    board.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(board)
    return _serialize(board)


@router.delete("/{board_id}")
def delete_board(board_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _ensure_ownership(db, user, board_id)
    db.delete(board)
    db.commit()
    return {"status": "success"}


@router.post("/{board_id}/items", response_model=MoodBoardOut, status_code=201)
def add_item(board_id: int, payload: MoodBoardItemCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _ensure_ownership(db, user, board_id)
    # Basic payload validation per kind — no fabricated media uploads.
    if payload.kind == "url":
        if "url" not in payload.payload or not str(payload.payload["url"]).startswith(("http://", "https://")):
            raise ValidationDomainError("mood-board url item requires payload.url http(s)://…")
    elif payload.kind == "product":
        if "product_id" not in payload.payload:
            raise ValidationDomainError("mood-board product item requires payload.product_id")
    elif payload.kind == "upload":
        # Real media-storage integration is out of scope for this PR — the
        # frontend would first upload the image to /uploads (which exists)
        # and then reference the returned filename here. We accept the
        # reference; we do NOT fake an upload result.
        if "upload_id" not in payload.payload:
            raise ValidationDomainError("mood-board upload item requires payload.upload_id (upload the file first)")

    next_position = 1 + (max((it.position for it in board.items), default=0))
    item = MoodBoardItem(
        board_id=board.id,
        kind=payload.kind,
        payload_json=json.dumps(payload.payload),
        position=next_position,
    )
    db.add(item)
    board.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(board)
    return _serialize(board)


@router.delete("/{board_id}/items/{item_id}", response_model=MoodBoardOut)
def remove_item(board_id: int, item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _ensure_ownership(db, user, board_id)
    item = db.query(MoodBoardItem).filter(MoodBoardItem.id == item_id, MoodBoardItem.board_id == board.id).first()
    if not item:
        raise ResourceNotFoundError("MoodBoardItem", item_id)
    db.delete(item)
    board.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(board)
    return _serialize(board)

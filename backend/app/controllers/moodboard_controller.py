"""Mood-board CRUD + real media upload — Group 1 §28.

Replaces the previous dead `user_style_profiles.moodboard_urls` column
with a proper owned table (mood_boards + mood_board_items). Every route
requires authentication and enforces ownership via profile_id → user_id
lookup — cross-user access is not possible.

Uploads are real: a multipart file is validated (content-type, size,
extension, path-traversal-safe object key), persisted to the configured
storage backend (local dir today, pluggable to object storage), and only
THEN referenced from a mood-board item. No fake upload ids, no base64
pretending to be storage, no memory-only files.
"""
import json
import os
import re
import uuid as _uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationDomainError,
)
from backend.app.models.profile import MoodBoard, MoodBoardItem, UserStyleProfile
from backend.app.models.user import User
from backend.app.services.storage_service import require_production_storage

# Real upload constraints (Group 1 §10/§12). Whitelist — never trust the
# client-supplied content_type or filename.
_ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _secure_upload(file: UploadFile, user_id: int, board_id: int, content: bytes) -> dict:
    """Validate + persist an uploaded image. Returns the stored reference.

    Object key is generated server-side (uuid + user/board scoping), never
    derived from the client filename → no path traversal, no overwrite of
    another user's asset, no extension spoofing.
    """
    # Durable storage is a deployment precondition (501 when absent in
    # production) — checked before any bytes are accepted.
    storage = require_production_storage("moodboard_upload")
    ctype = (file.content_type or "").lower()
    if ctype not in _ALLOWED_IMAGE_TYPES:
        raise ValidationDomainError(
            f"Unsupported content type '{ctype}'. Allowed: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))}"
        )
    if not content:
        raise ValidationDomainError("Uploaded file is empty.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationDomainError("File exceeds the 5 MB upload limit.")

    ext = _ALLOWED_IMAGE_TYPES[ctype]
    object_key = f"moodboards/u{user_id}/b{board_id}/{_uuid.uuid4().hex}{ext}"
    # The backend validates the key (traversal-safe) and returns the public URL
    # for whichever store is configured (local dev dir or S3/R2 in production).
    url = storage.store(object_key, content)
    return {"upload_id": object_key, "url": url, "content_type": ctype, "size": len(content)}

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
        # The file must already exist on the server via POST .../upload — we
        # verify the object key is present AND scoped to this user+board, so
        # a client cannot reference someone else's (or a nonexistent) asset.
        upload_id = str(payload.payload.get("upload_id", ""))
        expected_prefix = f"moodboards/u{user.id}/b{board.id}/"
        if not upload_id or not upload_id.startswith(expected_prefix):
            raise ValidationDomainError(
                "mood-board upload item requires payload.upload_id from POST /me/mood-boards/{board_id}/upload"
            )
        if ".." in upload_id:
            raise ValidationDomainError("Invalid upload reference.")
        # Existence is checked in the configured store (local dir in development,
        # S3/R2 in production) — the same backend that POST .../upload wrote to.
        if not require_production_storage("moodboard_upload").exists(upload_id):
            raise ValidationDomainError("Referenced upload does not exist on the server.")

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


@router.post("/{board_id}/upload", status_code=201)
async def upload_board_image(
    board_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Real multipart upload for a mood-board image (Group 1 §10).

    Flow: client multipart POST → validate content-type/size → persist to
    storage under a server-generated key → return the reference → client
    attaches it via POST .../items {kind:'upload', payload:{upload_id}}.
    """
    _ensure_ownership(db, user, board_id)
    content = await file.read()
    return _secure_upload(file, user.id, board_id, content)


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

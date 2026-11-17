"""Auth: PBKDF2 password hashing + JWT (PyJWT). Roles: student / admin."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from .db import User, get_db

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_token(email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": email, "role": role,
               "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
               "iat": now}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer),
                     db: Session = Depends(get_db)):
    if creds is None:
        raise HTTPException(401, "Missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin role required")
    return user

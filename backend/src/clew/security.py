"""Authentication and RBAC: pbkdf2 password hashing, JWT issue/verify, FastAPI role guards."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request

from .config import get_settings
from .db import get_db

ROLE_ORDER = {"viewer": 0, "editor": 1, "admin": 2}
PBKDF2_ITERATIONS = 240_000


def hash_password(plain: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_token(username: str, role: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=s.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def _bearer_payload(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer credentials")
    try:
        return jwt.decode(
            auth.removeprefix("Bearer "),
            get_settings().secret_key,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired credentials") from None


def current_user(request: Request) -> dict:
    payload = _bearer_payload(request)
    return {"username": payload["sub"], "role": payload["role"]}


def require_role(minimum: str):
    """Role guard dependency: declares the minimum role of the current route (viewer < editor < admin).

    The role is taken from the current database value (the role in the JWT is
    only issued at login), so after an admin changes someone's role the old
    token immediately takes effect with the new role.
    """

    def guard(user: dict = Depends(current_user)) -> dict:
        with get_db() as conn:
            row = conn.execute("SELECT role FROM user WHERE username=?",
                               (user["username"],)).fetchone()
        if row is None:
            raise HTTPException(401, "User does not exist or has been deleted")
        if ROLE_ORDER[row["role"]] < ROLE_ORDER[minimum]:
            raise HTTPException(403, f"Role {minimum} or higher is required")
        return {"username": user["username"], "role": row["role"]}

    return guard

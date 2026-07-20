"""JWT auth: bcrypt hashes, owner/viewer roles, bearer tokens.
Secrets come from env or a generated file under data/private/ (gitignored)."""
import os
import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from db import REPO_ROOT, utcnow

ALGO = "HS256"


def jwt_secret() -> str:
    env = os.environ.get("CAREERPILOT_JWT_SECRET")
    if env:
        return env
    path = REPO_ROOT / "data" / "private" / "jwt_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, pw_hash: str) -> bool:
    return bcrypt.checkpw(pw.encode(), pw_hash.encode())


def create_token(email: str, role: str, hours: int = 12) -> str:
    payload = {"sub": email, "role": role, "exp": utcnow() + timedelta(hours=hours)}
    return jwt.encode(payload, jwt_secret(), algorithm=ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[ALGO])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}")


def current_user(request: Request) -> dict:
    # the local runner authenticates with its service token and acts as owner
    # (same machine, same trust domain as the API's own database file)
    if request.headers.get("x-runner-token", "") == runner_token():
        return {"sub": "runner", "role": "owner"}
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    return decode_token(auth.split(None, 1)[1])


def require_owner(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "owner":
        raise HTTPException(403, "owner role required")
    return user


def runner_token() -> str:
    return os.environ.get("CAREERPILOT_RUNNER_TOKEN", "dev-local-runner")


def require_runner(request: Request) -> str:
    tok = request.headers.get("x-runner-token", "")
    if tok != runner_token():
        raise HTTPException(401, "bad runner token")
    return tok

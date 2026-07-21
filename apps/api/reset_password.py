"""Explicit owner-password reset — the ONLY way the password ever changes.

    .venv\\Scripts\\python apps/api/reset_password.py NEW_PASSWORD

Writes the bcrypt hash straight into the database; works whether or not the
API is running (the hash is read per login).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from auth import hash_password  # noqa: E402
from db import User, make_engine, make_session_factory  # noqa: E402


def reset(password: str, email: str | None = None) -> str:
    factory = make_session_factory(make_engine())
    with factory() as db:
        q = db.query(User).filter_by(role="owner")
        owner = q.filter_by(email=email).first() if email else q.first()
        if not owner:
            raise SystemExit("no owner user exists yet — start the API once first")
        owner.pw_hash = hash_password(password)
        db.commit()
        return owner.email


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        raise SystemExit("usage: python apps/api/reset_password.py NEW_PASSWORD")
    email = reset(sys.argv[1])
    print(f"password reset for {email}. It stays until you run this again.")

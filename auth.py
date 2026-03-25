# auth.py
# Centralised authentication and authorisation helpers.
# Uses Flask session (server-side) — no extra dependencies required.

from functools import wraps
from flask import session, redirect, url_for, flash, request
from databases import get_db
from models import User
import hashlib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """SHA-256 hash of a plain-text password.  Replace with bcrypt for production."""
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


def get_current_user():
    """Return the logged-in User ORM object, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = next(get_db())
    try:
        return db.query(User).filter(User.userId == user_id).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    """Redirect to login page if the user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """Restrict a route to users whose user_type is in *allowed_roles*.

    Usage:
        @role_required('blood_bank_staff')
        @role_required('blood_bank_staff', 'hospital_admin')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("main.login", next=request.path))

            user_type = session.get("user_type", "")

            # Admin bypass
            if user_type == "admin":
                return f(*args, **kwargs)

            if user_type not in allowed_roles:
                flash(
                    f"Access denied. Required role: {' or '.join(allowed_roles)}.",
                    "error",
                )
                return redirect(url_for("main.home_dashboard"))

            return f(*args, **kwargs)
        return decorated
    return decorator
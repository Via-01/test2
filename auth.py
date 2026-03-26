# auth.py
import hashlib
import uuid as _uuid
from functools import wraps
from datetime import datetime
from flask import session, redirect, url_for, flash, request
from databases import get_db
from models import User, AuditLog, LogAction, SCOPE_SYSTEM


def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = next(get_db())
    try:
        return db.query(User).filter(User.userId == uid).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit logging  — scoped version
# ---------------------------------------------------------------------------

def write_audit(db, action: LogAction, details: str,
                scope_type: str = SCOPE_SYSTEM, scope_id: str = None):
    """
    Write a scoped audit log entry.
    scope_type: 'blood_bank' | 'hospital' | 'system'
    scope_id  : blood bank unitId or hospital unitId
    """
    uid = session.get("user_id")
    if not uid:
        return
    try:
        db.add(AuditLog(
            logId      = str(_uuid.uuid4()),
            userId     = uid,
            timestamp  = datetime.utcnow(),
            type       = action,
            details    = details,
            scope_type = scope_type,
            scope_id   = scope_id,
        ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("main.login", next=request.path))
            user_type = session.get("user_type", "")
            if user_type == "admin":
                return f(*args, **kwargs)
            if user_type not in allowed_roles:
                flash(f"Access denied. Required role: {' or '.join(allowed_roles)}.", "error")
                return redirect(url_for("main.home_dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

"""JWT bearer-token auth + role/ownership helpers."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, request

from .errors import ApiError
from .extensions import db
from .models import User


def create_token(user):
    now = datetime.now(timezone.utc)
    minutes = current_app.config["JWT_EXPIRES_MINUTES"]
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _token_from_header():
    parts = request.headers.get("Authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ApiError(
            401, "unauthorized", "Missing or malformed Authorization header. Use 'Bearer <token>'."
        )
    return parts[1]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _token_from_header()
        try:
            payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = int(payload["sub"])
        except jwt.ExpiredSignatureError:
            raise ApiError(401, "token_expired", "Token has expired. Please log in again.")
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
            raise ApiError(401, "invalid_token", "Invalid authentication token.")
        # Load the user fresh so role changes / deletions take effect immediately.
        user = db.session.get(User, user_id)
        if user is None:
            raise ApiError(401, "invalid_token", "Invalid authentication token.")
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    def decorator(fn):
        @login_required
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.current_user.role not in roles:
                raise ApiError(403, "forbidden", "You do not have permission to perform this action.")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def can_manage_shelter(user, shelter_id):
    return user.role == "admin" or (user.role == "staff" and user.shelter_id == shelter_id)


def require_shelter_access(shelter_id):
    if not can_manage_shelter(g.current_user, shelter_id):
        raise ApiError(
            403, "forbidden", "You may only manage data belonging to your own shelter."
        )

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth_utils import create_token, login_required
from ..errors import ApiError
from ..extensions import db
from ..models import User
from ..validation import json_body, validate

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

# Used to keep login timing similar for unknown emails (avoids user enumeration by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password")

REGISTER_SCHEMA = {
    "email": {"type": "str", "required": True, "max_len": 255, "email": True, "lower": True},
    "password": {"type": "str", "required": True, "min_len": 8, "max_len": 128, "strip": False},
    "full_name": {"type": "str", "required": True, "max_len": 120},
}
LOGIN_SCHEMA = {
    "email": {"type": "str", "required": True, "max_len": 255, "lower": True},
    "password": {"type": "str", "required": True, "max_len": 128, "strip": False},
}


@bp.post("/register")
def register():
    clean = validate(json_body(), REGISTER_SCHEMA)
    if db.session.scalar(select(User.id).where(User.email == clean["email"])):
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    # Role is never taken from the request: self-registration always yields 'adopter'.
    user = User(email=clean["email"], full_name=clean["full_name"], role="adopter")
    user.set_password(clean["password"])
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    return jsonify(user.to_dict()), 201


@bp.post("/login")
def login():
    clean = validate(json_body(), LOGIN_SCHEMA)
    user = db.session.scalar(select(User).where(User.email == clean["email"]))
    if user is None:
        check_password_hash(_DUMMY_HASH, clean["password"])
        raise ApiError(401, "invalid_credentials", "Invalid email or password.")
    if not user.check_password(clean["password"]):
        raise ApiError(401, "invalid_credentials", "Invalid email or password.")
    return jsonify(
        {
            "access_token": create_token(user),
            "token_type": "Bearer",
            "expires_in": current_app.config["JWT_EXPIRES_MINUTES"] * 60,
            "user": user.to_dict(),
        }
    )


@bp.get("/me")
@login_required
def me():
    return jsonify(g.current_user.to_dict())

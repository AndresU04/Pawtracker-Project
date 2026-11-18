"""Admin-only user management (promote users to staff/admin)."""
from flask import Blueprint, jsonify
from sqlalchemy import select

from ..auth_utils import roles_required
from ..errors import ApiError
from ..extensions import db
from ..models import ROLES, Shelter, User
from ..validation import json_body, paginate, validate

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")

UPDATE_SCHEMA = {
    "role": {"type": "str", "choices": ROLES, "lower": True},
    "shelter_id": {"type": "int", "min": 1, "nullable": True},
}


@bp.get("")
@roles_required("admin")
def list_users():
    stmt = select(User).order_by(User.id)
    return jsonify(paginate(stmt, User.to_dict))


@bp.patch("/<int:user_id>")
@roles_required("admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "User not found.")
    clean = validate(json_body(), UPDATE_SCHEMA, partial=True)
    role = clean.get("role", user.role)
    shelter_id = clean.get("shelter_id", user.shelter_id)
    if role == "staff":
        if shelter_id is None:
            raise ApiError(422, "validation_error", "Request validation failed.",
                           {"shelter_id": "is required when role is 'staff'"})
        if db.session.get(Shelter, shelter_id) is None:
            raise ApiError(422, "validation_error", "Request validation failed.",
                           {"shelter_id": "does not exist"})
    else:
        shelter_id = None
    user.role = role
    user.shelter_id = shelter_id
    db.session.commit()
    return jsonify(user.to_dict())

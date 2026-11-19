from flask import Blueprint, g, jsonify
from sqlalchemy import func, select

from ..auth_utils import require_shelter_access, roles_required
from ..errors import ApiError
from ..extensions import db
from ..models import Animal, Shelter, User
from ..validation import json_body, paginate, validate

bp = Blueprint("shelters", __name__, url_prefix="/api/v1/shelters")

SHELTER_SCHEMA = {
    "name": {"type": "str", "required": True, "max_len": 150},
    "city": {"type": "str", "required": True, "max_len": 100},
    "address": {"type": "str", "max_len": 255, "nullable": True},
    "phone": {"type": "str", "max_len": 30, "nullable": True},
    "email": {"type": "str", "max_len": 255, "email": True, "nullable": True},
}


def _get_or_404(shelter_id):
    shelter = db.session.get(Shelter, shelter_id)
    if shelter is None:
        raise ApiError(404, "not_found", "Shelter not found.")
    return shelter


@bp.get("")
def list_shelters():
    stmt = select(Shelter).order_by(Shelter.name, Shelter.id)
    return jsonify(paginate(stmt, Shelter.to_dict))


@bp.get("/<int:shelter_id>")
def get_shelter(shelter_id):
    return jsonify(_get_or_404(shelter_id).to_dict())


@bp.post("")
@roles_required("admin")
def create_shelter():
    clean = validate(json_body(), SHELTER_SCHEMA)
    shelter = Shelter(**clean)
    db.session.add(shelter)
    db.session.commit()
    return jsonify(shelter.to_dict()), 201


@bp.route("/<int:shelter_id>", methods=["PUT", "PATCH"])
@roles_required("admin", "staff")
def update_shelter(shelter_id):
    shelter = _get_or_404(shelter_id)
    require_shelter_access(shelter.id)
    clean = validate(json_body(), SHELTER_SCHEMA, partial=True)
    for key, value in clean.items():
        setattr(shelter, key, value)
    db.session.commit()
    return jsonify(shelter.to_dict())


@bp.delete("/<int:shelter_id>")
@roles_required("admin")
def delete_shelter(shelter_id):
    shelter = _get_or_404(shelter_id)
    has_animals = db.session.scalar(
        select(func.count()).select_from(Animal).where(Animal.shelter_id == shelter.id)
    )
    has_staff = db.session.scalar(
        select(func.count()).select_from(User).where(User.shelter_id == shelter.id)
    )
    if has_animals or has_staff:
        raise ApiError(409, "shelter_not_empty",
                       "Cannot delete a shelter that still has animals or staff assigned.")
    db.session.delete(shelter)
    db.session.commit()
    return "", 204

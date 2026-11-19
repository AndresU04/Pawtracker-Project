from urllib.parse import urlencode

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from .. import cache
from ..auth_utils import require_shelter_access, roles_required
from ..errors import ApiError
from ..extensions import db
from ..models import ANIMAL_STATUSES, SEXES, SPECIES, Animal, Shelter
from ..validation import int_arg, json_body, paginate, validate

bp = Blueprint("animals", __name__, url_prefix="/api/v1/animals")

ANIMAL_SCHEMA = {
    "shelter_id": {"type": "int", "min": 1},
    "name": {"type": "str", "required": True, "max_len": 100},
    "species": {"type": "str", "required": True, "choices": SPECIES, "lower": True},
    "breed": {"type": "str", "max_len": 100, "nullable": True},
    "age_months": {"type": "int", "required": True, "min": 0, "max": 600},
    "sex": {"type": "str", "choices": SEXES, "lower": True, "nullable": True},
    "description": {"type": "str", "max_len": 2000, "nullable": True},
    # 'adopted' can only be reached via approving an application (atomic with the approval).
    "status": {"type": "str", "choices": ("available", "hold"), "lower": True},
}

SORT_FIELDS = {"created_at": Animal.created_at, "age_months": Animal.age_months, "name": Animal.name}


def _cached_json(key, build):
    hit = cache.get_json(key)
    if hit is not None:
        resp = jsonify(hit)
        resp.headers["X-Cache"] = "HIT"
        return resp
    payload = build()
    cache.set_json(key, payload)
    resp = jsonify(payload)
    resp.headers["X-Cache"] = "MISS"
    return resp


def _filtered_stmt():
    stmt = select(Animal)
    species = request.args.get("species")
    if species:
        if species.lower() not in SPECIES:
            raise ApiError(400, "invalid_query_param", "Unknown species. Use one of: " + ", ".join(SPECIES))
        stmt = stmt.where(Animal.species == species.lower())
    status = request.args.get("status")
    if status:
        if status.lower() not in ANIMAL_STATUSES:
            raise ApiError(400, "invalid_query_param", "Unknown status. Use one of: " + ", ".join(ANIMAL_STATUSES))
        stmt = stmt.where(Animal.status == status.lower())
    shelter_id = int_arg("shelter_id", minimum=1)
    if shelter_id is not None:
        stmt = stmt.where(Animal.shelter_id == shelter_id)
    breed = request.args.get("breed")
    if breed:
        stmt = stmt.where(Animal.breed == breed)
    min_age = int_arg("min_age_months", minimum=0)
    if min_age is not None:
        stmt = stmt.where(Animal.age_months >= min_age)
    max_age = int_arg("max_age_months", minimum=0)
    if max_age is not None:
        stmt = stmt.where(Animal.age_months <= max_age)
    q = request.args.get("q")
    if q:
        stmt = stmt.where(Animal.name.icontains(q, autoescape=True) | Animal.breed.icontains(q, autoescape=True))

    sort = request.args.get("sort", "-created_at")
    descending = sort.startswith("-")
    field = SORT_FIELDS.get(sort.lstrip("-"))
    if field is None:
        raise ApiError(400, "invalid_query_param", "sort must be one of: " + ", ".join(SORT_FIELDS) + " (prefix with '-' for descending).")
    stmt = stmt.order_by(field.desc() if descending else field.asc(), Animal.id)
    return stmt


@bp.get("")
def list_animals():
    qs = urlencode(sorted(request.args.items(multi=True)))
    key = f"animals:list:v{cache.version('animals')}:{qs}"
    return _cached_json(key, lambda: paginate(_filtered_stmt(), Animal.to_dict))


@bp.get("/<int:animal_id>")
def get_animal(animal_id):
    key = f"animals:detail:v{cache.version('animals')}:{animal_id}"

    def build():
        animal = db.session.get(Animal, animal_id)
        if animal is None:
            raise ApiError(404, "not_found", "Animal not found.")
        return animal.to_dict()

    return _cached_json(key, build)


@bp.post("")
@roles_required("staff", "admin")
def create_animal():
    clean = validate(json_body(), ANIMAL_SCHEMA)
    user = g.current_user
    shelter_id = clean.pop("shelter_id", None)
    if shelter_id is None and user.role == "staff":
        shelter_id = user.shelter_id
    if shelter_id is None:
        raise ApiError(422, "validation_error", "Request validation failed.", {"shelter_id": "is required"})
    require_shelter_access(shelter_id)
    if db.session.get(Shelter, shelter_id) is None:
        raise ApiError(422, "validation_error", "Request validation failed.", {"shelter_id": "does not exist"})
    animal = Animal(shelter_id=shelter_id, **clean)
    db.session.add(animal)
    db.session.commit()
    cache.bump("animals")
    return jsonify(animal.to_dict()), 201


@bp.route("/<int:animal_id>", methods=["PUT", "PATCH"])
@roles_required("staff", "admin")
def update_animal(animal_id):
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        raise ApiError(404, "not_found", "Animal not found.")
    require_shelter_access(animal.shelter_id)
    clean = validate(json_body(), ANIMAL_SCHEMA, partial=True)
    new_shelter = clean.pop("shelter_id", None)
    if new_shelter is not None and new_shelter != animal.shelter_id:
        if g.current_user.role != "admin":
            raise ApiError(403, "forbidden", "Only admins can move an animal to another shelter.")
        if db.session.get(Shelter, new_shelter) is None:
            raise ApiError(422, "validation_error", "Request validation failed.", {"shelter_id": "does not exist"})
        animal.shelter_id = new_shelter
    if animal.status == "adopted" and "status" in clean:
        raise ApiError(409, "animal_adopted", "An adopted animal's status cannot be changed here.")
    for key, value in clean.items():
        setattr(animal, key, value)
    db.session.commit()
    cache.bump("animals")
    return jsonify(animal.to_dict())


@bp.delete("/<int:animal_id>")
@roles_required("staff", "admin")
def delete_animal(animal_id):
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        raise ApiError(404, "not_found", "Animal not found.")
    require_shelter_access(animal.shelter_id)
    db.session.delete(animal)
    db.session.commit()
    cache.bump("animals")
    return "", 204

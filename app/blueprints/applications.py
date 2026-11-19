"""Adoption applications.

Consistency design (the key technical focus of PawTrack)
--------------------------------------------------------
Every state change that depends on an animal's status first takes a row lock on
that animal (SELECT ... FOR UPDATE), so concurrent requests for the same animal
are serialized by InnoDB:

* create:  lock animal -> check it is 'available' and the user has no active
           application -> insert.
* approve: lock animal -> lock application -> check both -> mark application
           approved, animal 'adopted', and auto-reject every other pending
           application for that animal -> COMMIT (all-or-nothing).

Lock order is always animal THEN application, so two requests cannot deadlock.
Checks after the lock are themselves locking reads / populate_existing, because
under MySQL's default REPEATABLE READ a plain SELECT could return a stale snapshot.
SQLite (used by the unit tests) ignores FOR UPDATE; the real concurrency test in
tests/test_concurrency.py runs against MySQL when TEST_DATABASE_URL is set.
"""
from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_, select, update

from .. import cache
from ..auth_utils import login_required, require_shelter_access, roles_required
from ..errors import ApiError
from ..extensions import db
from ..models import APPLICATION_STATUSES, AdoptionApplication, Animal, utcnow
from ..validation import int_arg, json_body, optional_json_body, paginate, validate

bp = Blueprint("applications", __name__, url_prefix="/api/v1/applications")

EDITABLE_FIELDS = {
    "applicant_name": {"type": "str", "max_len": 120},
    "applicant_email": {"type": "str", "max_len": 255, "email": True, "lower": True},
    "applicant_phone": {"type": "str", "max_len": 30, "nullable": True},
    "message": {"type": "str", "max_len": 5000, "nullable": True},
}
CREATE_SCHEMA = {"animal_id": {"type": "int", "required": True, "min": 1}, **EDITABLE_FIELDS}
DECISION_SCHEMA = {"decision_note": {"type": "str", "max_len": 500, "nullable": True}}


# ---------------------------------------------------------------- helpers
def _lock_animal(animal_id):
    return db.session.execute(
        select(Animal)
        .where(Animal.id == animal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _lock_application(application_id):
    return db.session.execute(
        select(AdoptionApplication)
        .where(AdoptionApplication.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _application_or_404(application_id):
    app_ = db.session.get(AdoptionApplication, application_id)
    if app_ is None:
        raise ApiError(404, "not_found", "Application not found.")
    return app_


def _can_view(user, app_):
    if user.role == "admin" or app_.applicant_id == user.id:
        return True
    return user.role == "staff" and user.shelter_id == app_.animal.shelter_id


# ---------------------------------------------------------------- create / read
@bp.post("")
@login_required
def create_application():
    user = g.current_user
    clean = validate(json_body(), CREATE_SCHEMA)

    animal = _lock_animal(clean["animal_id"])
    if animal is None:
        raise ApiError(422, "validation_error", "Request validation failed.",
                       {"animal_id": "does not exist"})
    if animal.status != "available":
        raise ApiError(409, "animal_unavailable",
                       f"This animal is not available for adoption (status: {animal.status}).")
    duplicate = db.session.execute(
        select(AdoptionApplication.id)
        .where(
            AdoptionApplication.animal_id == animal.id,
            AdoptionApplication.applicant_id == user.id,
            AdoptionApplication.status.in_(("pending", "approved")),
        )
        .with_for_update()
    ).first()
    if duplicate:
        raise ApiError(409, "duplicate_application",
                       "You already have an active application for this animal.")

    app_ = AdoptionApplication(
        animal_id=animal.id,
        applicant_id=user.id,
        applicant_name=clean.get("applicant_name", user.full_name),
        applicant_email=clean.get("applicant_email", user.email),
        applicant_phone=clean.get("applicant_phone"),
        message=clean.get("message"),
    )
    db.session.add(app_)
    db.session.commit()
    return jsonify(app_.to_dict()), 201


@bp.get("")
@login_required
def list_applications():
    user = g.current_user
    stmt = select(AdoptionApplication)
    if user.role == "staff":
        stmt = stmt.join(Animal, Animal.id == AdoptionApplication.animal_id).where(
            or_(Animal.shelter_id == user.shelter_id, AdoptionApplication.applicant_id == user.id)
        )
    elif user.role != "admin":
        stmt = stmt.where(AdoptionApplication.applicant_id == user.id)

    status = request.args.get("status")
    if status:
        if status.lower() not in APPLICATION_STATUSES:
            raise ApiError(400, "invalid_query_param",
                           "Unknown status. Use one of: " + ", ".join(APPLICATION_STATUSES))
        stmt = stmt.where(AdoptionApplication.status == status.lower())
    animal_id = int_arg("animal_id", minimum=1)
    if animal_id is not None:
        stmt = stmt.where(AdoptionApplication.animal_id == animal_id)
    stmt = stmt.order_by(AdoptionApplication.created_at.desc(), AdoptionApplication.id.desc())
    return jsonify(paginate(stmt, AdoptionApplication.to_dict))


@bp.get("/<int:application_id>")
@login_required
def get_application(application_id):
    app_ = _application_or_404(application_id)
    if not _can_view(g.current_user, app_):
        raise ApiError(403, "forbidden", "You do not have access to this application.")
    return jsonify(app_.to_dict())


# ---------------------------------------------------------------- update / delete
@bp.route("/<int:application_id>", methods=["PUT", "PATCH"])
@login_required
def update_application(application_id):
    user = g.current_user
    app_ = _application_or_404(application_id)
    if not (user.role == "admin" or app_.applicant_id == user.id):
        raise ApiError(403, "forbidden", "Only the applicant can edit this application.")
    clean = validate(json_body(), EDITABLE_FIELDS, partial=True)
    app_ = _lock_application(application_id)  # re-read under lock before checking state
    if app_ is None:
        raise ApiError(404, "not_found", "Application not found.")
    if app_.status != "pending":
        raise ApiError(409, "application_not_pending", "Only pending applications can be edited.")
    for key, value in clean.items():
        setattr(app_, key, value)
    db.session.commit()
    return jsonify(app_.to_dict())


@bp.delete("/<int:application_id>")
@login_required
def delete_application(application_id):
    user = g.current_user
    app_ = _application_or_404(application_id)
    is_owner = app_.applicant_id == user.id
    is_shelter = user.role == "admin" or (
        user.role == "staff" and user.shelter_id == app_.animal.shelter_id
    )
    if not (is_owner or is_shelter):
        raise ApiError(403, "forbidden", "You do not have access to this application.")
    app_ = _lock_application(application_id)
    if app_ is None:
        raise ApiError(404, "not_found", "Application not found.")
    if app_.status == "approved":
        raise ApiError(409, "application_approved", "Approved applications cannot be deleted.")
    if is_owner and not is_shelter and app_.status != "pending":
        raise ApiError(409, "application_not_pending", "Only pending applications can be withdrawn.")
    db.session.delete(app_)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------- decisions
def _decide(application_id, decision):
    user = g.current_user
    note = validate(optional_json_body(), DECISION_SCHEMA).get("decision_note")

    preview = db.session.get(AdoptionApplication, application_id)  # unlocked: only to find the animal
    if preview is None:
        raise ApiError(404, "not_found", "Application not found.")

    animal = _lock_animal(preview.animal_id)            # 1) lock animal
    require_shelter_access(animal.shelter_id)
    app_ = _lock_application(application_id)            # 2) lock application
    if app_ is None:
        raise ApiError(404, "not_found", "Application not found.")
    if app_.status != "pending":
        raise ApiError(409, "application_not_pending",
                       f"Application is already {app_.status}.")

    now = utcnow()
    if decision == "approved":
        if animal.status != "available":
            raise ApiError(409, "animal_unavailable",
                           f"Animal is no longer available (status: {animal.status}).")
        animal.status = "adopted"
        db.session.execute(
            update(AdoptionApplication)
            .where(
                AdoptionApplication.animal_id == animal.id,
                AdoptionApplication.status == "pending",
                AdoptionApplication.id != app_.id,
            )
            .values(
                status="rejected",
                decided_by=user.id,
                decided_at=now,
                decision_note="Another application for this animal was approved.",
            )
        )
    app_.status = decision
    app_.decided_by = user.id
    app_.decided_at = now
    app_.decision_note = note
    db.session.commit()                                  # atomic: all of the above or none
    if decision == "approved":
        cache.bump("animals")                            # catalog changed (animal now 'adopted')
    return jsonify(app_.to_dict())


@bp.post("/<int:application_id>/approve")
@roles_required("staff", "admin")
def approve_application(application_id):
    return _decide(application_id, "approved")


@bp.post("/<int:application_id>/reject")
@roles_required("staff", "admin")
def reject_application(application_id):
    return _decide(application_id, "rejected")

"""Relational schema (defined in code; created by `flask --app run init-db`).

Push 1.2 (Person 1): shared constants, helpers, Shelter and User only.
Later pushes add: Animal (Person 2), MedicalRecord (Person 4), AdoptionApplication (Person 3).
"""
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

SPECIES = ("dog", "cat", "rabbit", "bird", "other")
SEXES = ("male", "female", "unknown")
ANIMAL_STATUSES = ("available", "hold", "adopted")
RECORD_TYPES = ("vaccination", "treatment", "checkup", "surgery", "note")
APPLICATION_STATUSES = ("pending", "approved", "rejected")
ROLES = ("adopter", "staff", "admin")


def utcnow():
    """Naive UTC timestamps (MySQL DATETIME has no tz)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


class Shelter(db.Model):
    __tablename__ = "shelters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # NOTE: Person 2 adds the `animals` relationship line here in Push 2.1:
    #   animals = db.relationship("Animal", back_populates="shelter")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "city": self.city,
            "address": self.address,
            "phone": self.phone,
            "email": self.email,
            "created_at": iso(self.created_at),
        }


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="adopter")
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelters.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def set_password(self, password):
        # werkzeug default: scrypt with a per-password random salt
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "shelter_id": self.shelter_id,
            "created_at": iso(self.created_at),
        }
"""Relational schema (defined in code; created by `flask --app run init-db`).
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
    animals = db.relationship("Animal", back_populates="shelter")

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
        

class Animal(db.Model):
    __tablename__ = "animals"
    __table_args__ = (
        db.Index("ix_animals_species_status", "species", "status"),
        db.Index("ix_animals_shelter_status", "shelter_id", "status"),
        db.Index("ix_animals_status_created", "status", "created_at"),
        db.Index("ix_animals_breed", "breed"),
    )

    id = db.Column(db.Integer, primary_key=True)
    shelter_id = db.Column(
        db.Integer, db.ForeignKey("shelters.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(20), nullable=False)
    breed = db.Column(db.String(100))
    age_months = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(10))
    description = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="available")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    shelter = db.relationship("Shelter", back_populates="animals")
    applications = db.relationship("AdoptionApplication", back_populates="animal")

    def to_dict(self):
        return {
            "id": self.id,
            "shelter_id": self.shelter_id,
            "name": self.name,
            "species": self.species,
            "breed": self.breed,
            "age_months": self.age_months,
            "sex": self.sex,
            "description": self.description,
            "status": self.status,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class AdoptionApplication(db.Model):
    __tablename__ = "adoption_applications"
    __table_args__ = (
        db.Index("ix_apps_animal_status", "animal_id", "status"),
        db.Index("ix_apps_applicant", "applicant_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(
        db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False
    )
    applicant_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    applicant_name = db.Column(db.String(120), nullable=False)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_phone = db.Column(db.String(30))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending")
    decision_note = db.Column(db.String(500))
    decided_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    decided_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    animal = db.relationship("Animal", back_populates="applications")
    applicant = db.relationship("User", foreign_keys=[applicant_id])

    def to_dict(self):
        return {
            "id": self.id,
            "animal_id": self.animal_id,
            "applicant_id": self.applicant_id,
            "applicant_name": self.applicant_name,
            "applicant_email": self.applicant_email,
            "applicant_phone": self.applicant_phone,
            "message": self.message,
            "status": self.status,
            "decision_note": self.decision_note,
            "decided_by": self.decided_by,
            "decided_at": iso(self.decided_at),
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }

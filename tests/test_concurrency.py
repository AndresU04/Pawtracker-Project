"""Real concurrency test. SQLite ignores row locks, so this only runs against MySQL:

    TEST_DATABASE_URL=mysql+pymysql://pawtrack:pawtrack@127.0.0.1:3306/pawtrack_test pytest tests/test_concurrency.py

Use a throwaway database: the test creates and drops all tables.
"""
import os
import threading

import pytest

from app import create_app
from app.extensions import db
from app.models import AdoptionApplication, Animal, Shelter, User

URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not URL.startswith("mysql"), reason="set TEST_DATABASE_URL to a MySQL URL to run"
)


def test_only_one_of_many_concurrent_approvals_wins():
    app = create_app("testing", overrides={"SQLALCHEMY_DATABASE_URI": URL})
    n = 6
    with app.app_context():
        db.drop_all()
        db.create_all()
        shelter = Shelter(name="S", city="C")
        db.session.add(shelter)
        db.session.flush()
        staff = User(email="staff@t.io", full_name="Staff", role="staff", shelter_id=shelter.id)
        staff.set_password("Passw0rd!test")
        animal = Animal(shelter_id=shelter.id, name="Rex", species="dog", age_months=12)
        db.session.add_all([staff, animal])
        db.session.flush()
        app_ids = []
        for i in range(n):
            u = User(email=f"u{i}@t.io", full_name=f"U{i}", role="adopter")
            u.set_password("Passw0rd!test")
            db.session.add(u)
            db.session.flush()
            a = AdoptionApplication(animal_id=animal.id, applicant_id=u.id,
                                    applicant_name=u.full_name, applicant_email=u.email)
            db.session.add(a)
            db.session.flush()
            app_ids.append(a.id)
        db.session.commit()
        animal_id = animal.id

    login = app.test_client().post("/api/v1/auth/login",
                                   json={"email": "staff@t.io", "password": "Passw0rd!test"})
    headers = {"Authorization": "Bearer " + login.get_json()["access_token"]}

    statuses, barrier = [], threading.Barrier(n)

    def worker(application_id):
        client = app.test_client()
        barrier.wait()
        statuses.append(client.post(f"/api/v1/applications/{application_id}/approve",
                                    headers=headers).status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in app_ids]
    [t.start() for t in threads]
    [t.join() for t in threads]

    try:
        assert sorted(statuses) == [200] + [409] * (n - 1)
        with app.app_context():
            assert db.session.get(Animal, animal_id).status == "adopted"
            approved = db.session.query(AdoptionApplication).filter_by(status="approved").count()
            assert approved == 1
    finally:
        with app.app_context():
            db.session.remove()
            db.drop_all()

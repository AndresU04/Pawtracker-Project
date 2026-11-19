def _apply(client, headers, animal_id, **extra):
    return client.post("/api/v1/applications", json={"animal_id": animal_id, **extra}, headers=headers)


def test_apply_requires_auth(client, world):
    assert _apply(client, {}, world.animal).status_code == 401


def test_apply_success_defaults_applicant_info(client, world, auth):
    resp = _apply(client, auth(world.adopter1), world.animal, message="I love dogs")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["status"] == "pending" and body["applicant_email"] == world.adopter1


def test_apply_validation(client, world, auth):
    h = auth(world.adopter1)
    assert client.post("/api/v1/applications", json={}, headers=h).status_code == 422
    assert _apply(client, h, 9999).status_code == 422
    assert _apply(client, h, world.animal, applicant_email="bad").status_code == 422


def test_duplicate_application_409(client, world, auth):
    h = auth(world.adopter1)
    assert _apply(client, h, world.animal).status_code == 201
    dup = _apply(client, h, world.animal)
    assert dup.status_code == 409 and dup.get_json()["error"]["code"] == "duplicate_application"


def test_cannot_apply_to_unavailable_animal(client, world, auth):
    client.patch(f"/api/v1/animals/{world.animal}", json={"status": "hold"}, headers=auth(world.staff_a))
    resp = _apply(client, auth(world.adopter1), world.animal)
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "animal_unavailable"


def test_approve_is_atomic_and_auto_rejects_competitors(client, world, auth):
    a1 = _apply(client, auth(world.adopter1), world.animal).get_json()["id"]
    a2 = _apply(client, auth(world.adopter2), world.animal).get_json()["id"]
    staff = auth(world.staff_a)

    approved = client.post(f"/api/v1/applications/{a1}/approve", json={"decision_note": "Great home"}, headers=staff)
    assert approved.status_code == 200 and approved.get_json()["status"] == "approved"

    assert client.get(f"/api/v1/animals/{world.animal}").get_json()["status"] == "adopted"
    loser = client.get(f"/api/v1/applications/{a2}", headers=staff).get_json()
    assert loser["status"] == "rejected"

    # Second approval (the 'race loser') must fail cleanly.
    again = client.post(f"/api/v1/applications/{a2}/approve", headers=staff)
    assert again.status_code == 409
    assert client.post(f"/api/v1/applications/{a1}/approve", headers=staff).status_code == 409

    # New applications for an adopted animal are rejected.
    assert _apply(client, auth(world.admin), world.animal).status_code == 409


def test_approve_invalidates_catalog_cache(client, world, auth):
    a1 = _apply(client, auth(world.adopter1), world.animal).get_json()["id"]
    assert client.get("/api/v1/animals?status=available").get_json()["total"] == 1
    client.post(f"/api/v1/applications/{a1}/approve", headers=auth(world.staff_a))
    assert client.get("/api/v1/animals?status=available").get_json()["total"] == 0


def test_reject_leaves_animal_available(client, world, auth):
    a1 = _apply(client, auth(world.adopter1), world.animal).get_json()["id"]
    resp = client.post(f"/api/v1/applications/{a1}/reject", headers=auth(world.staff_a))
    assert resp.status_code == 200 and resp.get_json()["status"] == "rejected"
    assert client.get(f"/api/v1/animals/{world.animal}").get_json()["status"] == "available"


def test_decision_permissions(client, world, auth):
    a1 = _apply(client, auth(world.adopter1), world.animal).get_json()["id"]
    url = f"/api/v1/applications/{a1}/approve"
    assert client.post(url).status_code == 401
    assert client.post(url, headers=auth(world.adopter1)).status_code == 403   # applicant can't self-approve
    assert client.post(url, headers=auth(world.staff_b)).status_code == 403    # other shelter
    assert client.post("/api/v1/applications/9999/approve", headers=auth(world.staff_a)).status_code == 404
    assert client.post(url, headers=auth(world.admin)).status_code == 200


def test_list_visibility_scoping(client, world, auth):
    _apply(client, auth(world.adopter1), world.animal)
    _apply(client, auth(world.adopter2), world.animal)
    assert client.get("/api/v1/applications").status_code == 401
    assert client.get("/api/v1/applications", headers=auth(world.adopter1)).get_json()["total"] == 1
    assert client.get("/api/v1/applications", headers=auth(world.staff_a)).get_json()["total"] == 2
    assert client.get("/api/v1/applications", headers=auth(world.staff_b)).get_json()["total"] == 0
    assert client.get("/api/v1/applications", headers=auth(world.admin)).get_json()["total"] == 2
    assert client.get("/api/v1/applications?status=bogus", headers=auth(world.admin)).status_code == 400


def test_get_one_access_rules(client, world, auth):
    a1 = _apply(client, auth(world.adopter1), world.animal).get_json()["id"]
    url = f"/api/v1/applications/{a1}"
    assert client.get(url, headers=auth(world.adopter1)).status_code == 200
    assert client.get(url, headers=auth(world.staff_a)).status_code == 200
    assert client.get(url, headers=auth(world.adopter2)).status_code == 403
    assert client.get(url, headers=auth(world.staff_b)).status_code == 403


def test_owner_can_edit_pending_only(client, world, auth):
    h = auth(world.adopter1)
    a1 = _apply(client, h, world.animal).get_json()["id"]
    url = f"/api/v1/applications/{a1}"
    assert client.patch(url, json={"message": "updated"}, headers=h).get_json()["message"] == "updated"
    assert client.patch(url, json={"message": "hax"}, headers=auth(world.adopter2)).status_code == 403
    client.post(f"{url}/reject", headers=auth(world.staff_a))
    assert client.patch(url, json={"message": "late"}, headers=h).status_code == 409


def test_withdraw_and_delete_rules(client, world, auth):
    h = auth(world.adopter1)
    a1 = _apply(client, h, world.animal).get_json()["id"]
    url = f"/api/v1/applications/{a1}"
    assert client.delete(url, headers=auth(world.adopter2)).status_code == 403
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(url, headers=h).status_code == 404

    a2 = _apply(client, h, world.animal).get_json()["id"]
    client.post(f"/api/v1/applications/{a2}/approve", headers=auth(world.staff_a))
    assert client.delete(f"/api/v1/applications/{a2}", headers=h).status_code == 409  # approved: locked

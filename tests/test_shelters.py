
def test_shelters_public_read(client, world):
    resp = client.get("/api/v1/shelters")
    assert resp.status_code == 200 and resp.get_json()["total"] == 2
    assert client.get(f"/api/v1/shelters/{world.shelter_a}").status_code == 200
    assert client.get("/api/v1/shelters/9999").status_code == 404


def test_shelter_create_admin_only(client, world, auth):
    payload = {"name": "New Shelter", "city": "Anaheim"}
    assert client.post("/api/v1/shelters", json=payload).status_code == 401
    assert client.post("/api/v1/shelters", json=payload, headers=auth(world.staff_a)).status_code == 403
    resp = client.post("/api/v1/shelters", json=payload, headers=auth(world.admin))
    assert resp.status_code == 201


def test_shelter_validation(client, world, auth):
    resp = client.post("/api/v1/shelters", json={"city": "X"}, headers=auth(world.admin))
    assert resp.status_code == 422 and "name" in resp.get_json()["error"]["details"]


def test_staff_can_update_only_own_shelter(client, world, auth):
    ok = client.patch(f"/api/v1/shelters/{world.shelter_a}", json={"phone": "555-1234"},
                      headers=auth(world.staff_a))
    assert ok.status_code == 200 and ok.get_json()["phone"] == "555-1234"
    nope = client.patch(f"/api/v1/shelters/{world.shelter_b}", json={"phone": "1"},
                        headers=auth(world.staff_a))
    assert nope.status_code == 403


def test_cannot_delete_shelter_with_animals(client, world, auth):
    resp = client.delete(f"/api/v1/shelters/{world.shelter_a}", headers=auth(world.admin))
    assert resp.status_code == 409

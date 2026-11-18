VALID = {"name": "Milo", "species": "cat", "breed": "Tabby", "age_months": 10}


def test_public_list_and_pagination(client, world, auth):
    h = auth(world.staff_a)
    for i in range(5):
        client.post("/api/v1/animals", json={**VALID, "name": f"Cat{i}"}, headers=h)
    resp = client.get("/api/v1/animals?per_page=2&page=2")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["total"] == 6 and body["per_page"] == 2 and body["page"] == 2
    assert len(body["items"]) == 2 and body["pages"] == 3


def test_filters(client, world, auth):
    client.post("/api/v1/animals", json=VALID, headers=auth(world.staff_a))
    cats = client.get("/api/v1/animals?species=cat").get_json()
    assert cats["total"] == 1 and cats["items"][0]["name"] == "Milo"
    assert client.get("/api/v1/animals?species=dog&status=available").get_json()["total"] == 1
    assert client.get(f"/api/v1/animals?shelter_id={world.shelter_b}").get_json()["total"] == 0
    assert client.get("/api/v1/animals?q=beag").get_json()["total"] == 1


def test_bad_query_params_400(client):
    assert client.get("/api/v1/animals?species=dragon").status_code == 400
    assert client.get("/api/v1/animals?page=0").status_code == 400
    assert client.get("/api/v1/animals?per_page=1000").status_code == 400
    assert client.get("/api/v1/animals?page=abc").status_code == 400
    assert client.get("/api/v1/animals?sort=bogus").status_code == 400


def test_get_one_and_404(client, world):
    assert client.get(f"/api/v1/animals/{world.animal}").get_json()["name"] == "Rex"
    assert client.get("/api/v1/animals/9999").status_code == 404


def test_create_requires_auth_and_role(client, world, auth):
    assert client.post("/api/v1/animals", json=VALID).status_code == 401
    assert client.post("/api/v1/animals", json=VALID, headers=auth(world.adopter1)).status_code == 403


def test_staff_creates_in_own_shelter_by_default(client, world, auth):
    resp = client.post("/api/v1/animals", json=VALID, headers=auth(world.staff_a))
    assert resp.status_code == 201
    assert resp.get_json()["shelter_id"] == world.shelter_a and resp.get_json()["status"] == "available"


def test_staff_cannot_create_in_other_shelter(client, world, auth):
    resp = client.post("/api/v1/animals", json={**VALID, "shelter_id": world.shelter_b},
                       headers=auth(world.staff_a))
    assert resp.status_code == 403


def test_admin_must_name_shelter(client, world, auth):
    assert client.post("/api/v1/animals", json=VALID, headers=auth(world.admin)).status_code == 422
    ok = client.post("/api/v1/animals", json={**VALID, "shelter_id": world.shelter_b},
                     headers=auth(world.admin))
    assert ok.status_code == 201


def test_create_validation_422(client, world, auth):
    resp = client.post("/api/v1/animals",
                       json={"name": "", "species": "dragon", "age_months": -1},
                       headers=auth(world.staff_a))
    assert resp.status_code == 422
    assert {"name", "species", "age_months"} <= set(resp.get_json()["error"]["details"])


def test_update_own_and_forbidden_other_shelter(client, world, auth):
    ok = client.put(f"/api/v1/animals/{world.animal}", json={"age_months": 30},
                    headers=auth(world.staff_a))
    assert ok.status_code == 200 and ok.get_json()["age_months"] == 30
    nope = client.put(f"/api/v1/animals/{world.animal}", json={"age_months": 31},
                      headers=auth(world.staff_b))
    assert nope.status_code == 403


def test_cannot_set_adopted_directly(client, world, auth):
    resp = client.patch(f"/api/v1/animals/{world.animal}", json={"status": "adopted"},
                        headers=auth(world.staff_a))
    assert resp.status_code == 422


def test_delete_animal(client, world, auth):
    assert client.delete(f"/api/v1/animals/{world.animal}", headers=auth(world.staff_b)).status_code == 403
    assert client.delete(f"/api/v1/animals/{world.animal}", headers=auth(world.staff_a)).status_code == 204
    assert client.get(f"/api/v1/animals/{world.animal}").status_code == 404


def test_cache_hit_then_invalidated_on_update(client, world, auth):
    first = client.get("/api/v1/animals?species=dog")
    second = client.get("/api/v1/animals?species=dog")
    assert first.headers["X-Cache"] == "MISS" and second.headers["X-Cache"] == "HIT"

    client.patch(f"/api/v1/animals/{world.animal}", json={"name": "Rexy"}, headers=auth(world.staff_a))
    third = client.get("/api/v1/animals?species=dog")
    assert third.headers["X-Cache"] == "MISS"
    assert third.get_json()["items"][0]["name"] == "Rexy"
    detail = client.get(f"/api/v1/animals/{world.animal}")
    assert detail.get_json()["name"] == "Rexy"

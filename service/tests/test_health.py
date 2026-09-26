def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


def test_root_with_json_accept_header_returns_discovery_document(client):
    response = client.get("/", headers={"Accept": "application/json"}, follow_redirects=False)

    assert response.status_code == 200
    body = response.json()
    assert body["_links"]["self"]["href"].endswith("/")
    assert "sightings:create" in body["_links"]
    assert "sightings:live-sync" in body["_links"]
    assert "mqtt:broker" in body["_links"]


def test_root_with_jsonld_accept_header_returns_discovery_document(client):
    response = client.get("/", headers={"Accept": "application/ld+json"}, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/ld+json"
    body = response.json()
    assert body["@type"] == "Service"
    assert "sightings:create" in body["_links"]


def test_root_with_json_accept_header_keeps_plain_json_content_type(client):
    response = client.get("/", headers={"Accept": "application/json"}, follow_redirects=False)

    assert response.headers["content-type"] == "application/json"

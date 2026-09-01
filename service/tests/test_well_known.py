def test_oauth_protected_resource_document(client):
    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://localhost:8000",
        "authorization_servers": ["https://localhost:4444"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["sightings:ingest", "peer:write"],
    }

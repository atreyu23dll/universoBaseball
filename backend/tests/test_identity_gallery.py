"""Galería accesible sin crear universo, caché HTTP y límites de entrada."""


def test_gallery_api_exports_the_same_structured_identity_and_svg(client):
    response = client.get("/api/v1/identity-gallery")
    assert response.status_code == 200
    manifest = response.json()
    assert len(manifest["items"]) == manifest["total"] == 100
    detail = client.get("/api/v1/identity-gallery/0").json()["identity"]
    assert detail["profile"]["naming"]["official_name"] == manifest["items"][0]["name"]
    path = "/api/v1/identity-gallery/0/crest.svg?size=24"
    small = client.get(path)
    reduced = client.get(path + "&variant=reduced")
    assert small.text == reduced.text
    assert client.get(path, headers={"If-None-Match": small.headers["etag"]}).status_code == 304
    assert client.get("/api/v1/identity-gallery/100").status_code == 422
    assert client.get("/api/v1/identity-gallery?seed=-1").status_code == 422
    assert client.get(path + "&variant=invalid").status_code == 422
    for example in ("monogram", "elephant", "roses"):
        svg = client.get(f"/api/v1/identity-gallery/examples/{example}.svg")
        assert svg.status_code == 200
        assert svg.headers["content-type"].startswith("image/svg+xml")

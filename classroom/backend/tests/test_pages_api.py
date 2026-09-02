"""End-to-end behaviour of the page API against a mocked DynamoDB."""

from tests.conftest import OTHER_TEACHER, TEACHER, as_teacher


def create(client, **payload):
    return client.post("/api/pages", json=payload, environ_overrides=as_teacher(TEACHER))


def test_create_then_list_and_fetch(client):
    response = create(client, title="Warm Up: Slope", html="<p>Find the slope.</p>")
    assert response.status_code == 201
    page = response.get_json()
    assert page["title"] == "Warm Up: Slope"
    assert page["slug"].startswith("warm-up-slope-")
    assert page["published"] is False
    assert page["share_url"] is None

    listing = client.get("/api/pages", environ_overrides=as_teacher(TEACHER))
    assert listing.status_code == 200
    assert [p["id"] for p in listing.get_json()["pages"]] == [page["id"]]

    fetched = client.get(
        f"/api/pages/{page['id']}", environ_overrides=as_teacher(TEACHER)
    )
    assert fetched.status_code == 200
    assert fetched.get_json()["html"] == "<p>Find the slope.</p>"


def test_html_is_sanitized_on_write(client):
    response = create(
        client,
        title="Notes",
        html="<p>Keep</p><script>alert(1)</script>",
    )
    stored = response.get_json()["html"]
    assert "<p>Keep</p>" in stored
    assert "script" not in stored.lower()


def test_title_is_required(client):
    response = create(client, title="   ", html="<p>x</p>")
    assert response.status_code == 400
    assert "title is required" in response.get_json()["error"]


def test_unauthenticated_requests_are_rejected(client):
    # No authorizer claims on the environ at all.
    assert client.get("/api/pages").status_code == 401
    assert client.post("/api/pages", json={"title": "x"}).status_code == 401


def test_a_teacher_cannot_reach_another_teachers_page(client):
    page = create(client, title="Quiz", html="<p>secret</p>").get_json()

    for method in (client.get, client.delete):
        assert method(
            f"/api/pages/{page['id']}", environ_overrides=as_teacher(OTHER_TEACHER)
        ).status_code == 404

    assert client.put(
        f"/api/pages/{page['id']}",
        json={"title": "hijacked"},
        environ_overrides=as_teacher(OTHER_TEACHER),
    ).status_code == 404

    assert client.get(
        "/api/pages", environ_overrides=as_teacher(OTHER_TEACHER)
    ).get_json()["pages"] == []


def test_publishing_exposes_the_page_and_withdrawing_hides_it(client):
    page = create(client, title="Study Guide", html="<p>Chapter 4</p>").get_json()
    slug = page["slug"]

    # Unpublished: invisible to the public reader.
    assert client.get(f"/api/public/pages/{slug}").status_code == 404

    published = client.put(
        f"/api/pages/{page['id']}",
        json={"published": True},
        environ_overrides=as_teacher(TEACHER),
    ).get_json()
    assert published["published"] is True
    assert published["share_url"] == f"https://classroom.example.test/p/{slug}"

    public = client.get(f"/api/public/pages/{slug}")
    assert public.status_code == 200
    assert public.get_json()["title"] == "Study Guide"
    assert "script-src 'none'" in public.headers["Content-Security-Policy"]

    # Withdrawn: gone again, via the same slug.
    client.put(
        f"/api/pages/{page['id']}",
        json={"published": False},
        environ_overrides=as_teacher(TEACHER),
    )
    assert client.get(f"/api/public/pages/{slug}").status_code == 404


def test_editing_keeps_the_slug_stable(client):
    page = create(client, title="Warm Up", html="<p>a</p>").get_json()
    edited = client.put(
        f"/api/pages/{page['id']}",
        json={"title": "Warm Up (revised)", "html": "<p>b</p>"},
        environ_overrides=as_teacher(TEACHER),
    ).get_json()
    assert edited["title"] == "Warm Up (revised)"
    assert edited["slug"] == page["slug"]


def test_delete_removes_the_page(client):
    page = create(client, title="Scratch", html="<p>x</p>").get_json()
    assert client.delete(
        f"/api/pages/{page['id']}", environ_overrides=as_teacher(TEACHER)
    ).status_code == 200
    assert client.get(
        f"/api/pages/{page['id']}", environ_overrides=as_teacher(TEACHER)
    ).status_code == 404


def test_oversized_html_is_rejected(client):
    response = create(client, title="Huge", html="<p>" + ("x" * 300_000) + "</p>")
    assert response.status_code == 400
    assert "KB or smaller" in response.get_json()["error"]


def test_health_is_public(client):
    assert client.get("/api/public/health").get_json() == {"status": "ok"}

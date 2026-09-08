"""End-to-end behaviour of the page API against mocked DynamoDB and S3."""

from tests.conftest import OTHER_TEACHER, TEACHER, as_teacher, live_keys, upload


def create(client, **payload):
    return client.post("/api/pages", json=payload, headers=as_teacher(TEACHER))


def test_create_then_list_and_fetch(client):
    response = create(client, title="Warm Up: Slope")
    assert response.status_code == 201
    page = response.get_json()
    assert page["title"] == "Warm Up: Slope"
    assert page["published"] is False
    assert page["share_url"] is None
    # A page starts as an empty directory: no files, nothing to serve.
    assert page["file_count"] == 0

    listing = client.get("/api/pages", headers=as_teacher(TEACHER))
    assert [p["id"] for p in listing.get_json()["pages"]] == [page["id"]]


def test_title_is_required(client):
    response = create(client, title="   ")
    assert response.status_code == 400
    assert "title is required" in response.get_json()["error"]


def test_a_teacher_cannot_reach_another_teachers_page(client):
    page = create(client, title="Mine").get_json()
    response = client.get(
        f"/api/pages/{page['id']}", headers=as_teacher(OTHER_TEACHER)
    )
    assert response.status_code == 404


# --- uploads ---------------------------------------------------------------


def sign(client, page_id, paths):
    return client.post(
        f"/api/pages/{page_id}/uploads",
        json={"paths": paths},
        headers=as_teacher(TEACHER),
    )


def test_upload_signs_one_url_per_file(client):
    page = create(client, title="Fractions").get_json()
    response = sign(client, page["id"], ["index.html", "images/diagram.png", "quiz.js"])
    assert response.status_code == 200

    uploads = {u["path"]: u for u in response.get_json()["uploads"]}
    assert set(uploads) == {"index.html", "images/diagram.png", "quiz.js"}
    assert uploads["index.html"]["key"] == f"draft/{page['id']}/index.html"
    assert uploads["index.html"]["url"].startswith("https://")
    # The browser must send this exact header back or S3 rejects the signature.
    assert uploads["index.html"]["content_type"] == "text/html"
    assert uploads["images/diagram.png"]["content_type"] == "image/png"
    # Scripts are signed like anything else: lessons are interactive.
    assert uploads["quiz.js"]["content_type"] in ("text/javascript", "application/javascript")


def test_upload_requires_an_index(client):
    """Without index.html there is nothing for `/lesson/<id>/` to resolve to."""
    page = create(client, title="No index").get_json()
    response = sign(client, page["id"], ["notes.html"])
    assert response.status_code == 400
    assert "index.html" in response.get_json()["error"]


def test_upload_refuses_path_traversal(client):
    """The path becomes an S3 key a presigned URL grants write on."""
    page = create(client, title="Nasty").get_json()
    for bad in ["../other/index.html", "/etc/passwd", "a/../../b/index.html"]:
        response = sign(client, page["id"], ["index.html", bad])
        assert response.status_code == 400, bad
        assert "path" in response.get_json()["error"].lower()


def test_a_new_upload_replaces_the_previous_one(client, lessons_bucket):
    """A file she removed in her authoring tool must not survive the re-upload."""
    page = create(client, title="Replace").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    upload(lessons_bucket, page["id"], "old-slide.png")

    sign(client, page["id"], ["index.html"])

    listing = client.get(
        f"/api/pages/{page['id']}/files", headers=as_teacher(TEACHER)
    )
    assert listing.get_json()["files"] == []


# --- publish and withdraw --------------------------------------------------


def publish(client, page_id, value=True):
    return client.put(
        f"/api/pages/{page_id}",
        json={"published": value},
        headers=as_teacher(TEACHER),
    )


def test_publish_copies_files_to_the_served_prefix(client, lessons_bucket):
    page = create(client, title="Live one").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    upload(lessons_bucket, page["id"], "images/diagram.png", b"png")

    response = publish(client, page["id"])
    assert response.status_code == 200
    published = response.get_json()
    assert published["published"] is True
    assert published["file_count"] == 2
    # The share link is the lesson host and the page id, not the slug.
    assert published["share_url"].endswith(f"/lesson/{page['id']}/")

    assert live_keys(lessons_bucket, page["id"]) == ["images/diagram.png", "index.html"]


def test_publishing_nothing_is_refused(client):
    page = create(client, title="Empty").get_json()
    response = publish(client, page["id"])
    assert response.status_code == 400
    assert "uploaded" in response.get_json()["error"]


def test_withdraw_removes_the_served_copy_but_keeps_the_draft(client, lessons_bucket):
    page = create(client, title="On and off").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    publish(client, page["id"])

    response = publish(client, page["id"], value=False)
    assert response.status_code == 200
    assert response.get_json()["share_url"] is None
    assert live_keys(lessons_bucket, page["id"]) == []

    # The draft survived, so re-publishing restores the lesson.
    assert publish(client, page["id"]).status_code == 200
    assert live_keys(lessons_bucket, page["id"]) == ["index.html"]


def test_republishing_serves_the_new_upload(client, lessons_bucket):
    """A live lesson re-uploaded must not leave the class reading the old one."""
    page = create(client, title="Version two").get_json()
    upload(lessons_bucket, page["id"], "index.html", b"<h1>v1</h1>")
    upload(lessons_bucket, page["id"], "gone.png", b"x")
    publish(client, page["id"])
    assert live_keys(lessons_bucket, page["id"]) == ["gone.png", "index.html"]

    sign(client, page["id"], ["index.html"])
    upload(lessons_bucket, page["id"], "index.html", b"<h1>v2</h1>")
    client.post(
        f"/api/pages/{page['id']}/uploads/complete",
        headers=as_teacher(TEACHER),
    )

    assert live_keys(lessons_bucket, page["id"]) == ["index.html"]
    served = lessons_bucket.get_object(
        Bucket="classroom-test-lessons", Key=f"lesson/{page['id']}/index.html"
    )
    assert served["Body"].read() == b"<h1>v2</h1>"


def test_delete_removes_the_files_too(client, lessons_bucket):
    page = create(client, title="Bin it").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    publish(client, page["id"])

    response = client.delete(
        f"/api/pages/{page['id']}", headers=as_teacher(TEACHER)
    )
    assert response.status_code == 200
    assert live_keys(lessons_bucket, page["id"]) == []
    assert (
        client.get(f"/api/pages/{page['id']}", headers=as_teacher(TEACHER)).status_code
        == 404
    )


def test_health_is_the_only_public_route(client):
    assert client.get("/api/public/health").status_code == 200
    # The old anonymous JSON reader is gone; students read from CloudFront.
    assert client.get("/api/public/pages/anything").status_code == 404


# --- preview ---------------------------------------------------------------


def preview(client, page_id):
    return client.post(
        f"/api/pages/{page_id}/preview", headers=as_teacher(TEACHER)
    )


def test_preview_stages_the_draft_at_its_own_url(client, lessons_bucket):
    page = create(client, title="Check me").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    upload(lessons_bucket, page["id"], "js/quiz.js", b"x")

    response = preview(client, page["id"])
    assert response.status_code == 200
    previewed = response.get_json()

    # Its own id, NOT the page's — the whole reason this is separate.
    assert previewed["preview_url"] is not None
    assert f"/lesson/{page['id']}/" not in previewed["preview_url"]
    assert previewed["share_url"] is None  # previewing does not publish


def test_previewing_a_live_lesson_does_not_touch_what_students_read(
    client, lessons_bucket
):
    """The reason a preview cannot write to `lesson/<page-id>/`."""
    page = create(client, title="Live").get_json()
    upload(lessons_bucket, page["id"], "index.html", b"<h1>v1</h1>")
    publish(client, page["id"])

    # She edits and previews, but has not re-published.
    sign(client, page["id"], ["index.html"])
    upload(lessons_bucket, page["id"], "index.html", b"<h1>v2 draft</h1>")
    preview(client, page["id"])

    served = lessons_bucket.get_object(
        Bucket="classroom-test-lessons", Key=f"lesson/{page['id']}/index.html"
    )
    assert served["Body"].read() == b"<h1>v1</h1>", "students saw an unpublished edit"


def test_the_preview_link_is_stable_across_previews(client, lessons_bucket):
    """So she can leave the tab open and reload it."""
    page = create(client, title="Stable").get_json()
    upload(lessons_bucket, page["id"], "index.html")

    first = preview(client, page["id"]).get_json()["preview_url"]
    upload(lessons_bucket, page["id"], "index.html", b"<h1>changed</h1>")
    second = preview(client, page["id"]).get_json()["preview_url"]
    assert first == second


def test_previewing_nothing_is_refused(client):
    page = create(client, title="Empty").get_json()
    response = preview(client, page["id"])
    assert response.status_code == 400
    assert "uploaded" in response.get_json()["error"]


def test_delete_removes_the_preview_too(client, lessons_bucket):
    page = create(client, title="Bin").get_json()
    upload(lessons_bucket, page["id"], "index.html")
    preview_url = preview(client, page["id"]).get_json()["preview_url"]
    preview_id = preview_url.rstrip("/").rsplit("/", 1)[-1]

    client.delete(f"/api/pages/{page['id']}", headers=as_teacher(TEACHER))

    listing = lessons_bucket.list_objects_v2(
        Bucket="classroom-test-lessons", Prefix=f"lesson/{preview_id}/"
    )
    assert listing.get("KeyCount", 0) == 0

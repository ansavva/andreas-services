import pytest

from website_core.errors import ValidationError
from website_core.services import intake


def test_create_and_list(intake_table):
    intake.create_submission(
        {"email": "sam@acme.com", "message": "automate our invoice chasing", "name": "Sam"},
        source_page="/services",
    )
    result = intake.list_submissions()
    assert len(result["submissions"]) == 1

    row = result["submissions"][0]
    assert row["email"] == "sam@acme.com"
    assert row["name"] == "Sam"
    assert row["source_page"] == "/services"
    assert row["status"] == "new"
    assert "id" in row and "created_at" in row
    # Internal key attributes must not leak to the client.
    assert "PK" not in row and "SK" not in row


def test_invalid_email_rejected(intake_table):
    with pytest.raises(ValidationError):
        intake.create_submission({"email": "not-an-email", "message": "hi"})


def test_blank_message_rejected(intake_table):
    with pytest.raises(ValidationError):
        intake.create_submission({"email": "sam@acme.com", "message": "   "})


def test_listing_is_newest_first(intake_table):
    intake.create_submission({"email": "first@acme.com", "message": "one"})
    intake.create_submission({"email": "second@acme.com", "message": "two"})
    emails = [s["email"] for s in intake.list_submissions()["submissions"]]
    assert emails == ["second@acme.com", "first@acme.com"]


def test_long_message_is_capped(intake_table):
    intake.create_submission({"email": "sam@acme.com", "message": "x" * 10000})
    row = intake.list_submissions()["submissions"][0]
    assert len(row["message"]) == 5000

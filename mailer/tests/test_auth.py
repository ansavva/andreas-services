import pytest

from mailer.production.auth import authorize, normalize_principal, principal_from_event
from mailer.shared.config import ServiceConfig
from mailer.shared.errors import AuthorizationError


def service():
    return ServiceConfig(
        service_id="humbugg",
        sender_name="Humbugg",
        sender_address="no-reply@humbugg.com",
        allowed_categories=frozenset(),
        allowed_message_classes=frozenset(),
        allowed_role_arns=frozenset(
            {"arn:aws:iam::123456789012:role/humbugg-lambda-role-production"}
        ),
    )


def test_assumed_role_is_normalized():
    assert normalize_principal(
        "arn:aws:sts::123456789012:assumed-role/humbugg-lambda-role-production/session"
    ) == "arn:aws:iam::123456789012:role/humbugg-lambda-role-production"


def test_principal_is_read_from_http_api_event():
    event = {
        "requestContext": {
            "authorizer": {
                "iam": {
                    "userArn": (
                        "arn:aws:sts::123456789012:assumed-role/"
                        "humbugg-lambda-role-production/session"
                    )
                }
            }
        }
    }
    assert principal_from_event(event).endswith("role/humbugg-lambda-role-production")


def test_unregistered_role_is_rejected():
    with pytest.raises(AuthorizationError):
        authorize(service(), "arn:aws:iam::123456789012:role/storybook")

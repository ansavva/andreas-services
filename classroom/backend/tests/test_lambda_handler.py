"""The DEPLOYED path: a real API Gateway event through Mangum into Flask.

**This file exists because every other test missed a total production outage.**
Authenticated requests answered 401 in prod from the day the service was
created. The unit tests passed because they drive Flask directly, and local
development passed because the dev server stood in for the gateway and injected
an identity that the deployed path never actually supplies.

Nothing exercised `Mangum(WsgiToAsgi(app))`, which is the only arrangement that
runs in Lambda — and it is precisely where the claims were being dropped.
"""

import json

import pytest

from tests.conftest import TEACHER


class Context:
    aws_request_id = "test"
    function_name = "classroom-prod-api"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:us-east-1:704202188703:function:classroom-prod-api"

    def get_remaining_time_in_millis(self):
        return 30000


def gateway_event(method="GET", path="/api/pages", headers=None, body=None):
    """A REST API (v1) proxy event, the shape classroom's gateway sends."""
    return {
        "resource": path,
        "path": path,
        "httpMethod": method,
        "headers": {"Host": "classroom-api.andreas.services", **(headers or {})},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "requestContext": {
            "resourcePath": path,
            "httpMethod": method,
            "path": path,
            "stage": "prod",
            "requestId": "test",
            "identity": {"sourceIp": "1.2.3.4"},
            # The authorizer's claims. Deliberately PRESENT and deliberately
            # not what authenticates the request: they cannot reach Flask
            # through WsgiToAsgi, which is the whole point of this file.
            "authorizer": {"claims": {"sub": "someone-else", "email": "x@y.test"}},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


@pytest.fixture
def lambda_handler(dynamodb_table, lessons_bucket, verified_tokens):
    from classroom_core.handlers.aws.api import api_handler

    # Rebuilt per test so it binds to this test's mocked AWS backends.
    api_handler._mangum_handler = None
    return api_handler.handler


def test_authenticated_request_reaches_flask_with_an_identity(lambda_handler):
    """The regression. This returned 401 in production for the service's whole life."""
    response = lambda_handler(
        gateway_event(headers={"Authorization": f"Bearer test-token::{TEACHER['sub']}"}),
        Context(),
    )
    assert response["statusCode"] == 200, response["body"]
    assert json.loads(response["body"]) == {"pages": []}


def test_the_gateways_claims_are_not_what_authenticates(lambda_handler):
    """A request with the authorizer's claims but NO token is refused.

    Pins the decision rather than the accident: identity comes from the token on
    the header, so an event carrying claims and no `Authorization` must fail.
    Were this ever to pass, the app would be trusting a channel it cannot read.
    """
    response = lambda_handler(gateway_event(), Context())
    assert response["statusCode"] == 401


def test_a_bare_token_works_like_a_bearer_one(lambda_handler):
    """The SPA sends the raw ID token with no scheme; curl users type Bearer."""
    response = lambda_handler(
        gateway_event(headers={"Authorization": f"test-token::{TEACHER['sub']}"}),
        Context(),
    )
    assert response["statusCode"] == 200


def test_a_write_round_trips_through_the_adapter(lambda_handler):
    """Covers the body-length middleware on the deployed path as well."""
    response = lambda_handler(
        gateway_event(
            method="POST",
            path="/api/pages",
            headers={
                "Authorization": f"Bearer test-token::{TEACHER['sub']}",
                "Content-Type": "application/json",
            },
            body={"title": "Warm Up: Slope"},
        ),
        Context(),
    )
    assert response["statusCode"] == 201, response["body"]
    assert json.loads(response["body"])["title"] == "Warm Up: Slope"


def test_the_public_health_route_needs_no_token(lambda_handler):
    response = lambda_handler(gateway_event(path="/api/public/health"), Context())
    assert response["statusCode"] == 200

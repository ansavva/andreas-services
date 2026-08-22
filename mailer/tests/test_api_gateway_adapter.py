import asyncio
import json

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from mailer.adapters.aws.auth import IamAuthorizer, reset_principal, set_principal
from mailer.api.app_factory import create_app
from mailer.api.dependencies import ApiDependencies
from mailer.core.config import ServiceConfig

ROLE = "arn:aws:iam::123456789012:role/humbugg"
SERVICE = ServiceConfig(
    service_id="humbugg",
    sender_name="Humbugg",
    sender_address="no-reply@humbugg.com",
    allowed_categories=frozenset({"invitation"}),
    allowed_message_classes=frozenset({"exchange"}),
    allowed_role_arns=frozenset({ROLE}),
)
BODY = json.dumps(
    {
        "schema_version": 1,
        "application_message_id": "hmb_invitation_123",
        "category": "invitation",
        "message_class": "exchange",
        "to_address": "recipient@example.com",
        "subject": "Invitation",
        "html_body": "<p>Hello</p>",
        "text_body": "Hello",
        "attachments": [],
    }
)


class RecordingStore:
    def __init__(self):
        self.messages = []

    def register_attachment(self, service, upload, *, base_url=None):
        raise AssertionError("attachment registration was not expected")

    def admit_message(self, service, message):
        self.messages.append((service, message))


def _event(*, with_content_length=True):
    headers = {"content-type": "application/json", "host": "mailer.example.com"}
    if with_content_length:
        headers["content-length"] = str(len(BODY.encode()))
    return {
        "version": "2.0",
        "routeKey": "POST /v1/services/{service_id}/messages",
        "rawPath": "/v1/services/humbugg/messages",
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "domainName": "mailer.example.com",
            "http": {
                "method": "POST",
                "path": "/v1/services/humbugg/messages",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "requestId": "test",
            "stage": "$default",
        },
        "body": BODY,
        "isBase64Encoded": False,
    }


def _invoke(event):
    store = RecordingStore()
    app = create_app(
        ApiDependencies(
            services={"humbugg": SERVICE},
            store=store,
            authorizer=IamAuthorizer(),
        )
    )
    adapter = Mangum(WsgiToAsgi(app), lifespan="off")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    token = set_principal(ROLE)
    try:
        response = adapter(event, None)
    finally:
        reset_principal(token)
        loop.close()
        asyncio.set_event_loop(None)
    return response, store


def test_http_api_event_uses_shared_flask_routes_and_iam_context():
    response, store = _invoke(_event())

    assert response["statusCode"] == 202, response
    assert len(store.messages) == 1


def test_http_api_event_without_content_length_still_carries_its_body():
    # API Gateway does not reliably put Content-Length in the event's headers,
    # and asgiref derives CONTENT_LENGTH from nothing else — so without
    # BodyLengthMiddleware Werkzeug reads a zero-byte body and json_body
    # rejects a request that did send one.
    response, store = _invoke(_event(with_content_length=False))

    assert response["statusCode"] == 202, response
    assert len(store.messages) == 1

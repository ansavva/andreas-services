from __future__ import annotations

import json
from typing import Any

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from mailer.adapters.aws.auth import (
    IamAuthorizer,
    principal_from_event,
    reset_principal,
    set_principal,
)
from mailer.adapters.aws.config import load_service_registry
from mailer.adapters.aws.store import AwsStore
from mailer.api.app_factory import create_app
from mailer.api.dependencies import ApiDependencies
from mailer.core.errors import AuthorizationError

app = create_app(
    ApiDependencies(
        services=load_service_registry(),
        store=AwsStore(),
        authorizer=IamAuthorizer(),
    )
)
_mangum_handler = Mangum(WsgiToAsgi(app), lifespan="off")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        principal = principal_from_event(event)
    except AuthorizationError as error:
        return {
            "statusCode": 403,
            "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps({"error": "Forbidden", "message": str(error)}),
        }

    token = set_principal(principal)
    try:
        return _mangum_handler(event, context)
    finally:
        reset_principal(token)

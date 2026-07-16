from __future__ import annotations

import re
from typing import Any

from mailer.shared.config import ServiceConfig
from mailer.shared.errors import AuthorizationError

ASSUMED_ROLE = re.compile(r"^arn:aws:sts::(\d+):assumed-role/([^/]+)/[^/]+$")


def normalize_principal(arn: str) -> str:
    match = ASSUMED_ROLE.fullmatch(arn)
    if match:
        return f"arn:aws:iam::{match.group(1)}:role/{match.group(2)}"
    return arn


def principal_from_event(event: dict[str, Any]) -> str:
    context = event.get("requestContext", {})
    authorizer = context.get("authorizer", {})
    iam = authorizer.get("iam", {}) if isinstance(authorizer, dict) else {}
    identity = context.get("identity", {})
    raw = iam.get("userArn") or identity.get("userArn")
    if not raw:
        raise AuthorizationError("authenticated IAM principal is missing")
    return normalize_principal(raw)


def authorize(service: ServiceConfig, principal: str) -> None:
    if principal not in service.allowed_role_arns:
        raise AuthorizationError("caller is not registered for this service")

from __future__ import annotations

import os

from mailer.core.config import ServiceConfig, parse_service_registry
from mailer.core.errors import ValidationError


def load_service_registry() -> dict[str, ServiceConfig]:
    name = "MAILER_DEVELOPMENT_SERVICES_JSON"
    raw = os.environ.get(name)
    if not raw:
        raise ValidationError(f"{name} is required")
    return parse_service_registry(raw)

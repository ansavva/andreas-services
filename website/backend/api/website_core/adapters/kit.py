"""Kit (formerly ConvertKit) adapter — adds newsletter subscribers.

Uses the v3 form-subscribe endpoint. Kept on the stdlib (urllib) so the Lambda
image carries no extra HTTP dependency.
"""

import json
import urllib.error
import urllib.request

from website_core.common import config
from website_core.common.errors import ConfigError, UpstreamError

_BASE = "https://api.convertkit.com/v3"
_TIMEOUT = 10


def subscribe(email, first_name=None):
    """Add an email to the configured Kit form. Returns the Kit response body."""
    api_key = config.kit_api_key()
    form_id = config.kit_form_id()
    if not api_key or not form_id:
        raise ConfigError("Kit (ConvertKit) is not configured")

    payload = {"api_key": api_key, "email": email}
    if first_name:
        payload["first_name"] = first_name

    request = urllib.request.Request(
        f"{_BASE}/forms/{form_id}/subscribe",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise UpstreamError(f"Kit subscribe failed ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise UpstreamError("Kit subscribe failed (network)") from exc

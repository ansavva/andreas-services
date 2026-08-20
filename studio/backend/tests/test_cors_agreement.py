"""The four-place CORS agreement, as a check rather than a convention (#297).

**Why this file exists.** The browser's preflight is answered by API Gateway's
MOCK integration, not by Flask, so a verb this service starts accepting has to be
added in four places at once: `app_factory.CORS_METHODS`, the MOCK integration
response, and the `UNAUTHORIZED` and `ACCESS_DENIED` gateway responses. Miss one
and the SPA gets a network error with no status — the only failure in this
service that carries no message at all, and the reason `PATCH /api/text` is a
PATCH rather than the PUT you would expect.

Three of the four already share `local.cors_methods` in `modules/api_gateway`, so
the seam that can actually drift is this backend's list against that local. That
is what is asserted here, by reading the Terraform rather than trusting a comment
— the same tactic `humbugg`'s architecture tests use, and for the same reason: a
rule stated in prose is a rule until someone does not read it.

**What this cannot catch.** That the deployed stage is serving what the Terraform
says. A gateway response needs a redeployment to take effect, which is why
`aws_api_gateway_deployment.main` hashes the header *values* and not just
resource ids. Proving the live behaviour is a preflight against the deployed API,
which no unit test can do.
"""

import re
from pathlib import Path

from studio_core import app_factory
from studio_core.app_factory import create_app

# `HEAD` and `OPTIONS` are added by Werkzeug to every rule on its own, so they are
# not a claim this service makes about what it accepts.
IMPLICIT = {"HEAD", "OPTIONS"}


def _terraform_local(name: str) -> str:
    """One `local.<name> = "..."` value out of the api_gateway module.

    Read as text rather than parsed: a full HCL parser is a dependency, and this
    file has exactly one assignment per name.
    """
    source = (
        Path(__file__).resolve().parents[2] / "infra" / "modules" / "api_gateway" / "main.tf"
    ).read_text()
    match = re.search(rf'^\s*{name}\s*=\s*"([^"]*)"', source, re.M)
    assert match, f"local.{name} not found in modules/api_gateway/main.tf"
    return match.group(1)


def test_every_verb_the_api_accepts_is_in_the_cors_list():
    """The half a new route can break without touching either CORS definition."""
    registered = set()
    for rule in create_app().url_map.iter_rules():
        registered |= set(rule.methods or ()) - IMPLICIT

    assert registered <= set(app_factory.CORS_METHODS), (
        f"routes use {sorted(registered - set(app_factory.CORS_METHODS))}, "
        "which the CORS method list does not allow"
    )


def test_the_backend_and_the_gateway_allow_the_same_methods():
    """Flask's list against `local.cors_methods`, which the other three read."""
    assert app_factory.CORS_METHODS == _terraform_local("cors_methods").split(",")


def test_the_backend_and_the_gateway_allow_the_same_headers():
    """Same agreement, same failure mode.

    `X-Studio-Library` is the one that matters: a custom request header the
    browser has not been told is allowed fails the preflight, and #351 added it
    to both sides in the change that started reading it.
    """
    assert app_factory.CORS_HEADERS == _terraform_local("cors_headers").split(",")


def test_options_is_allowed_even_though_no_route_declares_it():
    """The preflight verb itself, which is answered before any route is reached."""
    assert "OPTIONS" in app_factory.CORS_METHODS

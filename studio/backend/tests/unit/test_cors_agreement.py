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

from tests.paths import INFRA_MODULES

import pytest

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
        INFRA_MODULES / "api_gateway" / "main.tf"
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


# ─────────────── the media bucket's CORS, which is a fifth place ───────────────
#
# Everything above is about the API. The upload added a CORS surface that has
# nothing to do with it: the bytes go browser → S3 directly, so the *bucket*
# answers that preflight and the API never sees the request at all.
#
# What can drift here is narrower than the API's four-way agreement and just as
# invisible. `s3.presign_put` puts `content-length` and `content-type` in
# `X-Amz-SignedHeaders`; the browser will not send a header the bucket's rule
# does not allow; so a rule missing one of them is an upload that fails the
# preflight with no status attached, in a service whose own tests all pass.
#
# Read out of the Terraform, as above, and for the same reason: a comment saying
# the two agree is a comment.


def _bucket_cors_headers(module: str) -> list[str]:
    """The `allowed_headers` of one storage module's CORS rule, lowercased.

    Regex rather than HCL parsing, matching `_terraform_local` — each module has
    exactly one `cors_rule`.
    """
    source = (
        INFRA_MODULES / module / "main.tf"
    ).read_text()
    match = re.search(r"allowed_headers\s*=\s*\[([^\]]*)\]", source)
    assert match, f"no cors_rule allowed_headers in modules/{module}/main.tf"
    return [value.strip().strip('"').lower() for value in match.group(1).split(",") if value.strip()]


@pytest.mark.parametrize("module", ["media", "dev_storage"])
def test_the_bucket_allows_every_header_the_upload_signature_requires(module):
    """Both buckets, because a rule on one of them is the worse failure.

    An upload that works in prod and fails locally — or the reverse — is a bug
    that only exists on one machine, and `modules/dev_storage` is a hand copy of
    `modules/media` by construction.
    """
    allowed = _bucket_cors_headers(module)

    assert "content-type" in allowed
    assert "content-length" in allowed


@pytest.mark.parametrize("module", ["media", "dev_storage"])
def test_the_bucket_allows_put_and_nothing_wider(module):
    """PUT is the whole grant. GET is not here on purpose — see `modules/media`.

    This fails the day somebody adds a method, which is the point: reads are
    served through the API precisely so this rule stays one line long, and
    widening it is a decision rather than a tidy-up.
    """
    source = (
        INFRA_MODULES / module / "main.tf"
    ).read_text()
    match = re.search(r"allowed_methods\s*=\s*\[([^\]]*)\]", source)
    assert match, f"no cors_rule allowed_methods in modules/{module}/main.tf"

    assert [value.strip().strip('"') for value in match.group(1).split(",")] == ["PUT"]


@pytest.mark.parametrize("module", ["media", "dev_storage"])
def test_no_bucket_allows_a_wildcard_origin(module):
    """A `*` would let any page a signed-in user visits complete an upload PUT.

    Terraform's own `validation` block refuses one passed in as a variable; this
    refuses one written into the resource, which that block cannot see.
    """
    source = (
        INFRA_MODULES / module / "main.tf"
    ).read_text()
    match = re.search(r"allowed_origins\s*=\s*(.+)", source)
    assert match, f"no cors_rule allowed_origins in modules/{module}/main.tf"

    assert "*" not in match.group(1)

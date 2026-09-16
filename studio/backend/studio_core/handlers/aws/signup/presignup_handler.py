"""Cognito's pre-sign-up trigger: the invite code is checked here, and nowhere else.

**It imports nothing from `studio_core` and that is the entire design**, for the
reason `hook/hook_handler.py` gives: this file is packaged by Terraform as a
plain zip straight out of the repo, with no ECR repository and no build step,
which is what lets the per-machine dev pool carry the same gate as prod.

## What this gate is for

The pool allows self sign-up so that an account can be made without an
administrator — `studio signup` from a terminal, or the SPA's sign-up page —
and every account that signs in can submit a generation billed to the one
provider token the API holds. So "anyone with an email" is not an acceptable
population, and this trigger is what narrows it: a sign-up carries the invite
code in `clientMetadata`, and a sign-up that does not carry the right one is
refused before Cognito creates anything.

## Why `clientMetadata`, and what that rules out

The `SignUp` API takes `ClientMetadata`, and it reaches this trigger verbatim.
The CLI sends it; the SPA sends it. **Cognito's own hosted sign-up page cannot**
— Managed Login has no field for it — so a sign-up started from the hosted page
arrives with no code and is refused with a message naming where to go instead.
That is deliberate: the hosted page is not a route this gate can cover, so it
is not a route in.

## Closed by default

The code arrives in `STUDIO_INVITE_CODE`. Empty or unset, every sign-up is
refused — a stack applied without the secret is a stack nobody can join, not a
stack anybody can. Compared with `hmac.compare_digest` so the refusal takes the
same time whatever was sent.

## Nothing else changes

`autoConfirmUser` and `autoVerifyEmail` are left false: the address still has
to receive a code and answer with it, which is what makes the verified email
the recovery channel `account_recovery_setting` names. Nothing here logs the
code, the attempt, or the address — a wrong code is a normal event on a public
endpoint, not an incident.
"""

import hmac
import os

#: The key `studio signup` and the SPA put the code under in `ClientMetadata`.
INVITE_KEY = "invite_code"

#: One sentence, no hint. Cognito shows this text to the person verbatim, and
#: adds its own full stop.
REFUSAL = (
    "Studio is invite-only. Sign up with `studio signup`, or at /signup on the "
    "app, with an invite code"
)


def handler(event, _context):
    """Return the event untouched to allow the sign-up; raise to refuse it."""
    expected = os.environ.get("STUDIO_INVITE_CODE", "")
    supplied = ((event.get("request") or {}).get("clientMetadata") or {}).get(INVITE_KEY, "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise Exception(REFUSAL)  # noqa: TRY002 - Cognito relays the message of any exception
    return event

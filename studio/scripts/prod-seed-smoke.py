# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.26"]
# ///
"""Converge the prod smoke account and the one library it may reach.

Run from `studio-prod.yaml` before the smoke suite, on every deploy:

    SMOKE_TEST_USER_PASSWORD=… uv run studio/scripts/prod-seed-smoke.py

## Why the pipeline seeds its own account

The alternative is a human creating it once and nobody noticing when it goes.
The pool is admin-create-only and the catalog has no code that writes a library,
so both halves of this account are hand-written rows — exactly the kind of state
that is restored by the next deploy here, or found a month later as a smoke
failure nobody can explain. Adding a second smoke identity later is then an edit
to `seeds/smoke.json` rather than another secret and another one-time step.

## Idempotence, and what a re-run actually does

Every step is read-then-write-if-absent, so a second run converges rather than
duplicating or failing:

* **The account** — created only if `admin_get_user` says it is not there.
* **The password** — set on *every* run, permanently. That is what makes
  rotating `SMOKE_TEST_USER_PASSWORD` converge: the next deploy resets the
  account to the new value instead of locking the suite out of it.
* **The library, its root node, the membership** — put under
  `attribute_not_exists(pk)`, so a row that exists is left exactly as it is.
  Where the existing row *disagrees* with the fixture this stops rather than
  rewriting: repointing a library at a different root node would strand every
  node beneath the old one.

## The isolation this enforces, and asserts

`app_factory`'s `before_request` resolves the library a request is about from
the caller's own membership rows. **A caller with exactly one membership can
only ever address that one library**, and every route then checks the node's own
`lib` against the same rows. So the whole of the smoke account's blast radius is
the set of memberships this script writes — which is one, always the library
`seeds/smoke.json` names, and never any other.

That is worth a check rather than a promise, so the last thing this does is read
the account's membership partition back and refuse to hand it to the suite
unless it holds exactly the one row. Nothing here reads, lists, writes or
deletes outside that library, and the refusal deliberately reports a **count**
rather than the ids it found: the remedy is to remove the extra membership by
hand, and printing another library's id into a CI log is not part of it.

## The password never appears

It arrives in the environment, is passed to one API call, and is never printed,
never logged, and never put in argv — an argument is readable in `ps` by every
other process on the machine for as long as the call takes. Every error below
names the *variable*, never its contents.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

FIXTURE = Path(__file__).resolve().parents[1] / "seeds" / "smoke.json"
PASSWORD_VAR = "SMOKE_TEST_USER_PASSWORD"
PASSWORD_PLACEHOLDER = f"${{{PASSWORD_VAR}}}"

# The two parameters `studio-prod.yaml` writes after every apply. Read rather
# than hard-coded for the reason the deploy workflow reads them: a pool or a
# table recreated by Terraform gets a new id, and a pinned one would seed into
# something that no longer serves traffic.
POOL_PARAMETER = "/studio/prod/cognito-user-pool-id"
TABLE_PARAMETER = "/studio/prod/catalog-table"

META = "META"


class SeedError(Exception):
    """Anything that should stop the deploy, with a message a human can act on."""


def _log(message: str) -> None:
    print(f"[smoke-seed] {message}", file=sys.stderr)


def _now() -> str:
    """The timestamp form `services.catalog` writes, to the microsecond."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _fixture() -> dict:
    try:
        parsed = json.loads(FIXTURE.read_text())
    except (OSError, ValueError) as error:
        raise SeedError(f"Could not read {FIXTURE}: {error}") from error

    library = parsed.get("library") or {}
    user = parsed.get("user") or {}
    missing = [
        name
        for name, value in (
            ("library.id", library.get("id")),
            ("library.name", library.get("name")),
            ("library.root_node", library.get("root_node")),
            ("user.email", user.get("email")),
            ("user.role", user.get("role")),
        )
        if not value
    ]
    if missing:
        raise SeedError(f"{FIXTURE} is missing: {', '.join(missing)}")

    # A real mailbox in this file would make a leak reach a person. `.test` is
    # reserved (RFC 2606) and resolves nowhere, which is the whole reason the
    # address is safe to commit — so it is checked here rather than trusted.
    if not str(user["email"]).endswith(".test"):
        raise SeedError(
            f"{FIXTURE} names an address outside the reserved .test TLD. "
            "Seeded identities must be unreachable by mail."
        )
    return {"library": library, "user": user}


def _password(user: dict) -> str:
    """The one secret, from the environment, or a refusal naming the variable."""
    declared = str(user.get("password") or "")
    if declared != PASSWORD_PLACEHOLDER:
        # A literal password in the fixture is a credential in the repository,
        # and this is the only place that would ever read it.
        raise SeedError(
            f"{FIXTURE} must declare the password as {PASSWORD_PLACEHOLDER}; "
            "it is never stored there."
        )
    value = os.environ.get(PASSWORD_VAR, "").strip()
    if not value:
        raise SeedError(
            f"refusing: fixture references {PASSWORD_PLACEHOLDER} and {PASSWORD_VAR} "
            "is unset or empty. An environment secret resolves to an empty string "
            "in silence when the job is missing its `environment:` key — check that "
            "first, then docs/PROD_SMOKE.md."
        )
    return value


def _parameter(ssm, name: str) -> str:
    try:
        value = ssm.get_parameter(Name=name)["Parameter"]["Value"]
    except ClientError as error:
        raise SeedError(f"Could not read {name}: {error}") from error
    if not value:
        raise SeedError(f"{name} resolved empty.")
    return value


# ──────────────────────────── Cognito ────────────────────────────


def _converge_account(cognito, pool_id: str, email: str, password: str) -> str:
    """Create the account if absent, set its password, and return its `sub`.

    `sub` and not the address: it is the pool's immutable id for the account and
    the claim the API reads out of the ID token, so it is the only thing a
    membership row can be keyed on.
    """
    try:
        user = cognito.admin_get_user(UserPoolId=pool_id, Username=email)
        _log(f"account exists in {pool_id}")
    except cognito.exceptions.UserNotFoundException:
        _log(f"creating the account in {pool_id}")
        # SUPPRESS because the password is set below rather than emailed, and
        # the address is a `.test` one that no mail could reach anyway.
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        user = cognito.admin_get_user(UserPoolId=pool_id, Username=email)

    # Every run, permanently. A newly created account is otherwise left in
    # FORCE_CHANGE_PASSWORD, where SRP sign-in returns a challenge instead of a
    # token; and setting it unconditionally is what makes a rotated secret
    # converge on the next deploy rather than locking the suite out.
    try:
        cognito.admin_set_user_password(
            UserPoolId=pool_id, Username=email, Password=password, Permanent=True
        )
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code == "InvalidPasswordException":
            raise SeedError(
                f"{PASSWORD_VAR} does not meet the pool's policy: 12+ characters "
                "with a lower-case letter, an upper-case letter and a digit. "
                "Re-run studio/scripts/prod-github-set-secrets.sh."
            ) from error
        raise SeedError(f"Could not set the account's password: {code or error}") from error

    sub = next(
        (attr["Value"] for attr in user.get("UserAttributes", []) if attr["Name"] == "sub"),
        "",
    )
    if not sub:
        raise SeedError("The pool returned an account with no `sub`.")
    return sub


# ──────────────────────────── the catalog ────────────────────────────


def _existing(dynamodb, table: str, pk: str, sk: str) -> dict | None:
    response = dynamodb.get_item(TableName=table, Key={"pk": {"S": pk}, "sk": {"S": sk}})
    return response.get("Item")


def _put_if_absent(dynamodb, table: str, item: dict) -> bool:
    """Write one item, or leave the one already there. True if it was written.

    The condition is what makes the read at each call site an optimisation
    rather than the check: two deploys racing would both see no row, and only
    one of them may write.
    """
    try:
        dynamodb.put_item(
            TableName=table, Item=item, ConditionExpression="attribute_not_exists(pk)"
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        return False
    return True


def _converge_library(dynamodb, table: str, library: dict) -> None:
    """The library row and its root node, created once and never rewritten."""
    lib, root, name = library["id"], library["root_node"], library["name"]
    now = _now()

    item = _existing(dynamodb, table, f"LIB#{lib}", META)
    if item:
        recorded = item.get("root_node", {}).get("S")
        if recorded != root:
            # Repointing a library at another root would strand every node
            # under the old one — invisible rows nothing lists and nothing
            # deletes. Whoever changed the fixture has to say what to do with
            # them.
            raise SeedError(
                f"{lib} already opens on a different root node than "
                f"{FIXTURE.name} names. Repointing it would strand everything "
                "beneath the current root; resolve it by hand."
            )
        _log(f"library {lib} exists")
    else:
        _log(f"creating library {lib}")
        _put_if_absent(
            dynamodb,
            table,
            {
                "pk": {"S": f"LIB#{lib}"},
                "sk": {"S": META},
                "name": {"S": name},
                "root_node": {"S": root},
                "created_at": {"S": now},
            },
        )

    item = _existing(dynamodb, table, f"NODE#{root}", META)
    if item:
        if item.get("lib", {}).get("S") != lib:
            raise SeedError(
                f"Node {root} belongs to a different library than {lib}. "
                "Refusing to touch it."
            )
        _log(f"root node {root} exists")
        return

    _log(f"creating root node {root}")
    # The shape `services.catalog` writes for a root: no `parent_id`, no
    # by-parent item, `path` of "/". Written literally because `catalog` is the
    # only module allowed to know these shapes and it has no function that
    # creates a library — a seeder built from its helpers would agree with any
    # drift in them.
    _put_if_absent(
        dynamodb,
        table,
        {
            "pk": {"S": f"NODE#{root}"},
            "sk": {"S": META},
            "node_id": {"S": root},
            "lib": {"S": lib},
            "name": {"S": name},
            "kind": {"S": "folder"},
            "path": {"S": "/"},
            "created_at": {"S": now},
            "updated_at": {"S": now},
        },
    )


def _converge_membership(dynamodb, table: str, sub: str, lib: str, role: str) -> None:
    """The one row that decides everything this account can reach."""
    if _existing(dynamodb, table, f"USER#{sub}", f"LIB#{lib}"):
        _log(f"membership in {lib} exists")
        return
    _log(f"granting membership in {lib}")
    _put_if_absent(
        dynamodb,
        table,
        {
            "pk": {"S": f"USER#{sub}"},
            "sk": {"S": f"LIB#{lib}"},
            "role": {"S": role},
            "created_at": {"S": _now()},
        },
    )


def _assert_one_membership(dynamodb, table: str, sub: str, lib: str) -> None:
    """Refuse to hand the account to the suite unless it reaches one library.

    This is the check the whole exercise rests on. One query on one partition —
    the account's own — and the only acceptable answer is the single row above.

    **The failure names a count and not the ids.** A second membership is
    somebody's hand-written row, the remedy is to delete it, and neither of
    those needs another library's id printed into a CI log.
    """
    paginator = dynamodb.get_paginator("query")
    sort_keys = [
        item["sk"]["S"]
        for page in paginator.paginate(
            TableName=table,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": {"S": f"USER#{sub}"}},
        )
        for item in page.get("Items", [])
    ]

    if sort_keys == [f"LIB#{lib}"]:
        _log(f"membership check: exactly one, {lib}")
        return

    raise SeedError(
        f"REFUSING TO CONTINUE: the smoke account holds {len(sort_keys)} memberships, "
        f"expected exactly 1 ({lib}). One membership is what makes this account "
        "structurally unable to address any other library — the API resolves a "
        "request's library from these rows. Remove the extra membership before "
        "the smoke suite is allowed near a token."
    )


def main() -> int:
    try:
        fixture = _fixture()
        library, user = fixture["library"], fixture["user"]
        password = _password(user)

        region = os.environ.get("AWS_REGION") or "us-east-1"
        ssm = boto3.client("ssm", region_name=region)
        pool_id = os.environ.get("USER_POOL_ID") or _parameter(ssm, POOL_PARAMETER)
        table = os.environ.get("CATALOG_TABLE") or _parameter(ssm, TABLE_PARAMETER)

        cognito = boto3.client("cognito-idp", region_name=region)
        dynamodb = boto3.client("dynamodb", region_name=region)

        sub = _converge_account(cognito, pool_id, user["email"], password)
        _converge_library(dynamodb, table, library)
        _converge_membership(dynamodb, table, sub, library["id"], user["role"])
        _assert_one_membership(dynamodb, table, sub, library["id"])
    except SeedError as error:
        _log(f"error: {error}")
        return 1
    except ClientError as error:
        # AccessDenied lands here. The CI role carries `cognito-idp:*` and
        # `dynamodb:*` on `*` (infra/envs/shared/main.tf), so a denial means the
        # job is running as something else.
        _log(f"error: {error}")
        return 1

    _log("seeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

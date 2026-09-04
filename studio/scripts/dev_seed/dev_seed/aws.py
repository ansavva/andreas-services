"""AWS access and stack selection, for a tool that is not the studio CLI.

**This is the only reason `dev-seed` is a separate project rather than a
subcommand.** Every other `studio` command reaches the library through the API
and holds no cloud credential, which is the property that makes the CLI safe to
hand to an agent. Seeding cannot work that way: it writes the node rows and
copies the blobs that a library is *made of*, server-side, before there is a
signed-in session or in many cases a library at all. So it needs a DynamoDB
client and an S3 client of its own — five DynamoDB functions, two S3, and a
config read.
"""
from __future__ import annotations

import configparser
import decimal
import os
import pathlib
import sys

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

#: The same file `studio profile` writes. Read rather than shelled out to,
#: because this tool is meant to work on a machine whose `studio` is not
#: installed — a fresh checkout provisioning its first stack is the case.
CONFIG_FILE = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    / "andreas-services" / "studio" / "config"
)

ENV_VAR = {
    "s3_bucket": "STUDIO_S3_BUCKET",
    "catalog_table": "STUDIO_CATALOG_TABLE",
    # `load` reads it to name the pool a fresh stack's accounts live in.
    "cognito_user_pool_id": "STUDIO_COGNITO_USER_POOL_ID",
}


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def profile_name() -> str:
    """Which stack to talk to. `dev` unless told otherwise, and never prod by default.

    `--profile`/`STUDIO_PROFILE` is honoured so `dev-seed` and `studio` agree
    about which stack is in force, but the default is `dev` here for a stronger
    reason than convenience: `publish` reads a stack and `load` writes one, and
    a tool that guessed production for either would be a hard-rule-#1 incident
    (`publish`) or a prod overwrite (`load`). `source()` refuses a prod-named
    bucket outright as the mechanical half of the same rule.
    """
    return os.environ.get("STUDIO_PROFILE") or "dev"


def value(field: str) -> str:
    """One stack field: the environment first, then the profile, then a refusal.

    The environment wins so a caller can point this at a stack the profile does
    not describe — `STUDIO_DEV_MACHINE_ID` targeting somebody else's stack is
    the case that needs it. There is deliberately no fallback to a production
    name: a command run in an unloaded shell must fail, not address prod.
    """
    from_env = os.environ.get(ENV_VAR[field])
    if from_env:
        return from_env

    name = profile_name()
    parser = configparser.ConfigParser()
    if CONFIG_FILE.is_file():
        parser.read(CONFIG_FILE)
        found = parser.get(name, field, fallback=None)
        if found:
            return found

    die(
        f"{ENV_VAR[field]} is not set and profile {name!r} does not supply it.\n"
        f"       Create it once with:  studio profile sync {name}\n"
        f"       Or set {ENV_VAR[field]} in the environment."
    )


def bucket() -> str:
    return value("s3_bucket")


def table() -> str:
    return value("catalog_table")


def session():
    return boto3.session.Session(region_name=REGION)


def client():
    """An S3 client."""
    return session().client("s3")


def ddb_client():
    return session().client("dynamodb")


# ── marshalling ─────────────────────────────────────────────────────────────
#
# Two conversions, each paid for by a real failure. Both are load-bearing and
# neither is obvious.


def to_item(doc: dict) -> dict:
    """A plain dict -> DynamoDB's typed attribute map, `None`s dropped.

    **Every `float` becomes a `Decimal` first.** `TypeSerializer` refuses a
    float outright — DynamoDB's N is a decimal type and boto3 will not guess a
    binary-float rounding — so a document holding one raised `TypeError: Float
    types are not supported` from three frames inside boto3, naming nothing
    about which attribute was at fault. The conversion goes through `str`, so
    0.8 is stored as 0.8 rather than as the seventeen digits its binary
    representation actually is.
    """
    return {k: TypeSerializer().serialize(_decimals(v))
            for k, v in doc.items() if v is not None}


def from_item(item: dict) -> dict:
    """The inverse, with numbers as ints.

    **It recurses.** A top-level-only conversion is invisible while every row
    is flat, and an ENTITY row is not: a character carries a nested `profile`,
    so a count two maps deep would reach `json.dumps` as a Decimal
    and die with "Object of type Decimal is not JSON serializable" halfway
    through writing the fixture.
    """
    deserializer = TypeDeserializer()
    return {key: _plain(deserializer.deserialize(val)) for key, val in item.items()}


def _decimals(value):
    if isinstance(value, float):
        return decimal.Decimal(str(value))
    if isinstance(value, dict):
        return {k: _decimals(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_decimals(v) for v in value]
    return value


def _plain(value):
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, set):
        # A DynamoDB set deserialises to a `set`, which json.dumps also refuses.
        # Sorted rather than arbitrary, so a fixture file diffs.
        return sorted(_plain(v) for v in value)
    return value


def scan(ddb, **kwargs):
    """Every item in the table, paginated.

    A scan rather than a GSI query on purpose: the indexes are the API's read
    path, and a GSI drops any row missing one of its key attributes — which is
    exactly the row a fixture must not silently omit.
    """
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=table(), **kwargs):
        for item in page.get("Items", []):
            yield from_item(item)


def table_exists(ddb) -> bool:
    try:
        ddb.describe_table(TableName=table())
    except ddb.exceptions.ResourceNotFoundException:
        return False
    return True

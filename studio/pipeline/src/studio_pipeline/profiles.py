"""Named environments for the CLI — `dev`, `prod`, and any other you sync.

**One decision, made in one place: which stack is this invocation talking to?**
Before this, the answer was spread over five environment variables that three
different scripts exported and one `.env` file pinned, and nothing printed the
result. Two of those variables (`STUDIO_S3_BUCKET`, `STUDIO_CATALOG_TABLE`)
selected a *different* stack from the other three, so a shell could be signed in
to one environment and running `catalog gc` against another with no symptom.

Modelled on the AWS CLI's `~/.aws/config`, and deliberately unlike it in one
respect — see "An explicit profile wins" below.

## The files

    ~/.config/andreas-services/studio/
    ├── config          this file's subject: per-profile TARGETING. Ids and
    │                   names only, nothing secret, safe to read out loud.
    ├── credentials     tokens, keyed by profile (`adapters/auth.py`)
    ├── dev.env         that profile's account email + password
    ├── prod.env        likewise
    └── machine-id

`<profile>.env` is not new and is not read here. `dev-aws-common.sh` and
`create-user.sh` already used exactly that naming for the two account files, and
the profile names are chosen to match what is already on disk.

**Nothing secret goes in `config`.** Every value in it is a resource name or an
id: the same five `dev-up.sh` exports into a shell, and the same ones sitting
unencrypted in SSM under `/studio/prod/`. Passwords stay in `<profile>.env` at
mode 600, and `REPLICATE_API_TOKEN` is **not a profile field and is no longer
read by this package at all** — generation moved into the API (#536), so the
provider credential is the API's: an SSM SecureString in prod, and
`~/.config/andreas-services/studio/dev.env` for a local one under `dev-up.sh`.
It was never environment-scoped, which is why it was never a profile field.

## An explicit profile wins, including over the environment

| Given | What decides all five values |
|---|---|
| `--profile prod`, or `STUDIO_PROFILE=prod` | the profile, and only the profile |
| neither | the environment, then the current profile, then `studio/.env` |

The first row is the one that matters and it has to be that way round. `dev-up.sh`
exports `STUDIO_API_URL` and both Cognito ids into the shell it runs in. If an
exported variable beat an explicit `--profile prod`, then typing that in a
`dev-up.sh` shell would silently keep talking to dev — you would believe you
were looking at production and you would not be. So an explicit profile
overrides, and says so on stderr when it is overriding something that disagrees.

**This is the mirror image of the AWS CLI, on purpose.** There, naming a profile
makes the CLI resolve that profile *and stop* — it will not fall back to ambient
credentials, and it will not let them win either. `scripts/dev-aws-common.sh`
documents at length what that cost: on a machine whose credentials arrive as
environment variables, every call failed `NoCredentials` while a bare
`aws sts get-caller-identity` two lines earlier succeeded. Naming a profile
should tell you *more* about where you are pointing, not less.

The second row is what every existing caller gets, unchanged: `dev-up.sh`, the
backend integration harness and `tests/conftest.py` all set the environment
variables directly and none of them passes `--profile`.

## There is no gate on writing to production

Selecting a profile is treated as sufficient intent, the same way `aws --profile`
is. Hard rule #2 is unaffected and still applies wherever it applied before: a
generation shows its full payload and waits for a yes, whichever profile is
selected. What a profile changes is that the target is now stated rather than
inferred — `studio whoami` names it, and `studio profile show` says where each
value came from.

**A profile is not a permission boundary and must not be mistaken for one** —
though there is far less behind it than there was. This used to warn that the
maintenance commands reached S3 and DynamoDB under your own IAM key. Those
commands are deleted; the only AWS call left in this package is `aws_session()`
below, which `profile sync` uses to read a stack's Terraform outputs and prod's
SSM parameters. Selecting `prod` still does not narrow what that key can do.
"""

from __future__ import annotations

import configparser
import os
import sys

from studio_pipeline import CONFIG_DIR, env_value
from studio_pipeline.errors import die

CONFIG_FILE = CONFIG_DIR / "config"

#: The section holding this file's own settings rather than a profile.
#: A real `[DEFAULT]` would be wrong: configparser copies its keys into every
#: other section, so `current = prod` would appear as a field of every profile.
META_SECTION = "studio"

DEFAULT_PROFILE = "dev"

#: The five values that decide which stack an invocation talks to, and the
#: environment variable each has always been spelled as. The env names are not
#: an implementation detail — `dev-up.sh`, `backend/tests/integration/conftest.py`
#: and the Lambda's own configuration all use them, so they stay the fallback
#: path and stay spelled the same.
FIELDS = (
    "api_url",
    "cognito_user_pool_id",
    "cognito_client_id",
    "s3_bucket",
    "catalog_table",
)

ENV_VAR = {
    "api_url": "STUDIO_API_URL",
    "cognito_user_pool_id": "STUDIO_COGNITO_USER_POOL_ID",
    "cognito_client_id": "STUDIO_COGNITO_CLIENT_ID",
    "s3_bucket": "STUDIO_S3_BUCKET",
    "catalog_table": "STUDIO_CATALOG_TABLE",
}

#: Set by the root group's `--profile`, which also reads `STUDIO_PROFILE`.
#: Module state rather than a Click context object because `value()` is called
#: from places that have no context — `adapters/auth.py` on every request, and
#: the tests.
_selected: str | None = None

#: Stderr warnings already emitted, so a command making forty API calls does not
#: print the same override notice forty times.
_warned: set[str] = set()


class ProfileError(RuntimeError):
    """A profile was named that does not exist, or is missing a field."""


# ── selection ───────────────────────────────────────────────────────────────


def select(name: str | None) -> None:
    """Record the explicitly-chosen profile. Called once, by the root group."""
    global _selected
    _selected = name.strip() if name and name.strip() else None
    _warned.clear()


def selected() -> str | None:
    """The explicitly-chosen profile, or None if nobody chose one."""
    return _selected


def current() -> str:
    """The profile in force: explicit, then the recorded default, then `dev`."""
    if _selected:
        return _selected
    return _meta().get("current", DEFAULT_PROFILE)


# ── the config file ─────────────────────────────────────────────────────────


def _parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if CONFIG_FILE.is_file():
        parser.read(CONFIG_FILE)
    return parser


def _write(parser: configparser.ConfigParser) -> None:
    """Persist, 600 and inside a 700 directory.

    Nothing here is secret — see the module docstring — but the directory
    already holds two password files and a machine id at those modes, and one
    file in it with looser permissions is a thing nobody would notice.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        parser.write(handle)


def _meta() -> dict:
    parser = _parser()
    return dict(parser[META_SECTION]) if parser.has_section(META_SECTION) else {}


def _section(name: str) -> dict:
    parser = _parser()
    if name == META_SECTION or not parser.has_section(name):
        return {}
    return {k: v.strip() for k, v in parser[name].items() if v.strip()}


def fields(name: str) -> dict:
    """One profile's stored fields, exactly as written. No env, no fallbacks.

    The raw read, for the callers that are asking *about* a profile rather than
    resolving the one in force — `adapters/auth.py` matching a token's issuer
    against every profile's pool, and `studio profile list`.
    """
    return _section(name)


def names() -> list[str]:
    """Every profile in the config file, in file order."""
    return [s for s in _parser().sections() if s != META_SECTION]


def exists(name: str) -> bool:
    return name in names()


def save(name: str, values: dict) -> None:
    """Write one profile's fields, replacing that section and no other."""
    if name == META_SECTION:
        raise ProfileError(f"{META_SECTION!r} is reserved and cannot be a profile name.")
    parser = _parser()
    if not parser.has_section(name):
        parser.add_section(name)
    for field in FIELDS:
        if values.get(field):
            parser.set(name, field, str(values[field]))
    if values.get("source"):
        parser.set(name, "source", str(values["source"]))
    _write(parser)


def set_current(name: str) -> None:
    """Record the profile used when no `--profile` and no env var is given."""
    if not exists(name):
        raise ProfileError(
            f"No profile named {name!r}. Create it with: studio profile sync {name}"
        )
    parser = _parser()
    if not parser.has_section(META_SECTION):
        parser.add_section(META_SECTION)
    parser.set(META_SECTION, "current", name)
    _write(parser)


# ── resolution ──────────────────────────────────────────────────────────────


def _legacy(field: str) -> str:
    """`studio/.env` and the config dir's `dev.env`, via the package's own reader.

    Kept for `s3_bucket` and `catalog_table`, which `dev-setup.sh` pinned into
    `studio/.env` for a year. A checkout that has one of those lines and no
    synced profile goes on working; `studio profile sync dev` is what replaces
    it, and `studio profile show` says which one answered.
    """
    return (env_value(ENV_VAR[field]) or "").strip()


def resolve(field: str) -> tuple[str, str]:
    """`(value, source)` for one field. Empty value means nothing supplied one.

    `source` is for `studio profile show` and for error messages — it is the
    difference between "you have not synced this profile" and "something in your
    shell is pointing you somewhere else".
    """
    if field not in ENV_VAR:  # pragma: no cover - programming error
        raise ProfileError(f"unknown profile field {field!r}")

    name = current()
    from_profile = _section(name).get(field, "")
    from_env = (os.environ.get(ENV_VAR[field]) or "").strip()

    if _selected:
        _warn_if_overriding(name, field, from_profile, from_env)
        return from_profile, f"profile {name}"

    if from_env:
        return from_env, f"${ENV_VAR[field]}"
    if from_profile:
        return from_profile, f"profile {name}"
    legacy = _legacy(field)
    if legacy:
        return legacy, "studio/.env"
    return "", "unset"


def _warn_if_overriding(name: str, field: str, from_profile: str, from_env: str) -> None:
    """Say so when an explicit profile is beating a variable that disagrees.

    Silence here is what would make the override rule dangerous rather than
    safe: a `dev-up.sh` shell exports three of these, and someone who has
    forgotten that should be told which one is winning, not left to infer it
    from a 404.
    """
    if not from_env or from_env.rstrip("/") == from_profile.rstrip("/"):
        return
    key = f"{name}:{field}"
    if key in _warned:
        return
    _warned.add(key)
    print(
        f"note: --profile {name} overrides ${ENV_VAR[field]} "
        f"({from_env} → {from_profile or 'unset'})",
        file=sys.stderr,
    )


def value(field: str, *, required: bool = True) -> str:
    """One resolved field, or a refusal that names the fix.

    Every caller asks through here rather than reading a module constant, so
    "unset" cannot be discovered halfway through a paginate — the property
    `adapters/s3.bucket()` and `adapters/ddb.table()` already had, now with one
    resolver behind both.
    """
    resolved, _ = resolve(field)
    if not resolved and required:
        die(missing(field))
    return resolved


def missing(field: str) -> str:
    """The refusal to print when `field` resolved to nothing.

    Public because the callers do not all die the same way: `adapters/s3.py` and
    `adapters/ddb.py` exit through `errors.die`, while `adapters/auth.py` raises
    `AuthError` so that `whoami` can report an unreachable API instead of
    vanishing. One message, two exits.
    """
    name = current()
    if _selected:
        return (
            f"profile {name!r} does not define {field}.\n"
            f"       Sync it from the stack it names:\n"
            f"         studio profile sync {name}\n"
            f"       studio profile list  shows what exists."
        )
    return (
        f"{ENV_VAR[field]} is not set and no profile supplies it.\n"
        f"       Pick an environment explicitly:\n"
        f"         studio --profile dev <command>     # this machine's dev stack\n"
        f"         studio --profile prod <command>    # the deployed library\n"
        f"       Create them once with: studio profile sync dev\n"
        f"       There is deliberately no default: this used to fall back to\n"
        f"       production, which is not a thing to guess at."
    )


def describe(name: str | None = None) -> list[tuple[str, str, str]]:
    """`(field, value, source)` for each field, for `studio profile show`."""
    global _selected
    previous = _selected
    if name is not None:
        _selected = name
    try:
        return [(field, *resolve(field)) for field in FIELDS]
    finally:
        _selected = previous


# ── syncing a profile from the stack it names ───────────────────────────────


STATE_BUCKET = "andreas-services-terraform-state"
MACHINE_ID_FILE = CONFIG_DIR / "machine-id"
PROD_SSM_PATH = "/studio/prod"

#: Where the CLI reaches a dev stack. There is no deployed dev API — `dev-up.sh`
#: runs the Flask app locally against this machine's stack — so a dev profile's
#: api_url is localhost by construction rather than by lookup.
DEV_API_URL = "http://localhost:8000"


def sync_dev(*, api_url: str = DEV_API_URL) -> dict:
    """This machine's dev stack, read from its Terraform state object.

    The same source `dev-aws-common.sh:load_dev_stack_outputs` reads, and for
    the same reason it reads it that way: a caller that only wants a pool id
    should not have to `terraform init`, reconfigure a backend and download a
    provider to find out, and this works from a cold checkout with no
    `.terraform` directory.
    """
    import json

    if not MACHINE_ID_FILE.is_file():
        raise ProfileError(
            f"No machine id at {MACHINE_ID_FILE} — this machine has no dev stack.\n"
            "Provision one with: ./studio/scripts/dev-aws-setup.sh"
        )
    machine_id = MACHINE_ID_FILE.read_text().strip().lower()

    session = aws_session()
    account = session.client("sts").get_caller_identity()["Account"]
    key = f"studio/dev/{account}/{machine_id}/terraform.tfstate"
    try:
        body = session.client("s3").get_object(Bucket=STATE_BUCKET, Key=key)["Body"].read()
    except Exception as error:  # noqa: BLE001 - botocore raises a generated class
        raise ProfileError(
            f"Terraform state is missing at s3://{STATE_BUCKET}/{key}.\n"
            "Provision the stack with: ./studio/scripts/dev-aws-setup.sh"
        ) from error

    outputs = json.loads(body).get("outputs", {})

    def out(name: str) -> str:
        return str(outputs.get(name, {}).get("value") or "")

    values = {
        "api_url": api_url,
        "cognito_user_pool_id": out("cognito_user_pool_id"),
        "cognito_client_id": out("cognito_user_pool_client_id"),
        "s3_bucket": out("media_bucket_name"),
        "catalog_table": out("catalog_table_name"),
        "source": f"terraform:{key}",
    }
    _require_complete("dev", values)
    return values


def sync_prod() -> dict:
    """The deployed stack, from the SSM parameters the deploy workflow writes.

    SSM rather than Terraform state, and the difference is the point: these are
    what the *deploy* wrote, so they cannot drift from what is actually serving.
    That is the same argument `dev-up.sh` makes for reading dev's values from
    Terraform instead — nothing deploys a dev stack, and nothing but the deploy
    writes these.
    """
    ssm = aws_session().client("ssm")
    found: dict[str, str] = {}
    token = None
    while True:
        kwargs = {"Path": PROD_SSM_PATH, "Recursive": True}
        if token:
            kwargs["NextToken"] = token
        page = ssm.get_parameters_by_path(**kwargs)
        for parameter in page.get("Parameters", []):
            found[parameter["Name"].rsplit("/", 1)[-1]] = parameter["Value"]
        token = page.get("NextToken")
        if not token:
            break

    values = {
        "api_url": found.get("api-domain", ""),
        "cognito_user_pool_id": found.get("cognito-user-pool-id", ""),
        "cognito_client_id": found.get("cognito-client-id", ""),
        "s3_bucket": found.get("media-bucket", ""),
        "catalog_table": found.get("catalog-table", ""),
        "source": f"ssm:{PROD_SSM_PATH}",
    }
    _require_complete("prod", values)
    return values


def _require_complete(name: str, values: dict) -> None:
    missing = [f for f in FIELDS if not values.get(f)]
    if missing:
        raise ProfileError(
            f"the {name} stack did not supply {', '.join(missing)} — "
            "refusing to write a half-made profile."
        )


SYNCERS = {"dev": sync_dev, "prod": sync_prod}


# ── the one boto3 call site left in the CLI ─────────────────────────────────


def aws_session():
    """A boto3 session, for `profile sync` and for nothing else.

    **This is the whole of the CLI's remaining AWS surface, and it is here
    rather than in `adapters/` on purpose.** `adapters/s3.py` and
    `adapters/ddb.py` held the clients that `catalog verify | gc | reseat`,
    `backfill-plans`, `drop-fictional` and `dev-seed` reached the library
    through; all of those are gone — the API records a sweep row instead of
    leaving orphans to be found by a bucket scan, the migrations are over, and
    seeding is its own project under `scripts/dev_seed/`. Nothing in `adapters/`
    opens an AWS client now, which is what #308 was actually asking for.

    `sync` cannot go through the API for the reason nothing else here needs an
    exception: it is how the CLI *finds* the API. Reading a dev stack's
    Terraform outputs and prod's SSM parameters is the step that produces the
    URL every other command then talks to.

    boto3's own chain resolves the credentials. The `aws configure
    export-credentials` bridge that used to wrap this is deleted with the module
    that held it: it was mandatory under the `aws login` sessions neither boto3
    nor the Terraform provider could see, and since August 2026 the credential
    is a long-lived access key that boto3 reads natively.
    """
    try:
        import boto3
    except ImportError:  # pragma: no cover — declared in pyproject
        die("boto3 is not installed — run `uv sync` in studio/pipeline.")
    region = (os.environ.get("AWS_REGION")
              or os.environ.get("AWS_DEFAULT_REGION")
              or "us-east-1")
    return boto3.session.Session(region_name=region)

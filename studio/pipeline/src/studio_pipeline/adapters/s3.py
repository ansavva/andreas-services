# Direct S3 access for the code that still needs it: credential resolution + a
# boto3 S3 client, plus bucket/prefix config and small utilities. Not run
# directly.
#
# The three modules named here — s3_upload.py / s3_download.py / s3_presign.py —
# were the script-era callers and none of them exists; the skill this called
# itself helpers for was rewritten by #406 and describes the API, not a bucket.
# What imports it now is `adapters/ddb.py` (for the session) and the three
# `maintenance/` commands, which reach S3 and DynamoDB straight because they
# reconcile the two against each other. Everything else goes through
# `adapters/store.py`.
#
# Credentials: since August 2026 these are a long-lived access key — `[default]`
# in `~/.aws/credentials`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in the
# environment — and boto3's own chain reads both. The `aws configure
# export-credentials` bridge below is kept as a fallback rather than deleted:
# it was mandatory under the `aws login` (login_session) sessions this replaced,
# which neither boto3 nor the Terraform provider could see, and it still covers
# an SSO or credential_process profile. Explicit AWS_ACCESS_KEY_ID in the
# environment wins and skips it entirely.
import json
import os
import subprocess

from studio_pipeline.errors import die

# STUDIO_S3_*, not XHARNESS_S3_*. The bucket was renamed to
# `studio-prod-media-us-east-1` and the variables were renamed with it, which is
# load-bearing rather than tidiness: `dev-setup.sh` only writes the variable
# when it is absent, so every developer with an older `.env` carried a pinned
# `XHARNESS_S3_BUCKET=xharness-...` that would have quietly kept the pipeline
# writing to the archive after the cutover. Renaming the variable makes that
# stale line inert instead of silently wrong.
# **No default, and the absence is the point.** This read
# `os.environ.get("STUDIO_S3_BUCKET", "studio-prod-media-us-east-1")`, so a
# maintenance command run in a shell that had not loaded `studio/.env` addressed
# PRODUCTION. Three commands read this and one of them is `catalog gc`, which
# deletes objects — a dry run against the wrong bucket lists prod's orphans, and
# the `--apply` that follows removes them.
#
# The same reasoning as the `XHARNESS_S3_*` rename directly above: a value that
# quietly points somewhere plausible is worse than no value. Unset is now a
# refusal at the point of use rather than a silent redirection.
BUCKET = os.environ.get("STUDIO_S3_BUCKET", "")


def bucket() -> str:
    """The media bucket, or a refusal naming what to do about it.

    Every AWS-touching command asks for it through here rather than reading
    `BUCKET`, so "unset" cannot be discovered halfway through a paginate.
    """
    if not BUCKET:
        die("STUDIO_S3_BUCKET is not set.\n"
            "       Run studio/scripts/dev-setup.sh, or export it for the stack you\n"
            "       mean. There is deliberately no default: this used to fall back to\n"
            "       the production bucket, which is not a thing to guess at.")
    return BUCKET
# `PREFIX` / `STUDIO_S3_PREFIX` lived here and is deleted too. The tree is at
# the bucket ROOT, and this had survived as "the single place a global prefix
# could be reintroduced" — but the only reader left was the layout migrator,
# and that went with the migration it served. A seam nothing sits behind is not
# a seam; reintroducing one is a decision, and it should be made where the
# module that needs it lives rather than pre-declared here.
#
# `MEDIA_PREFIX` / `STUDIO_S3_MEDIA_PREFIX` lived here and is deleted. It was
# the pre-restructure `media/` wrapper, described as "used only by the
# migrator" — and by the time it was removed nothing read it at all, migrator
# included. A variable a reader can find, and set, and get no behaviour from is
# worse than no variable: it reads as configuration. If a `.env` still pins it,
# delete the line.
REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)




def _resolve_credentials():
    """Return a dict of boto3 credential kwargs, or None to use boto3's own chain."""
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return None  # explicit env creds — let boto3 pick them up
    try:
        # `--format process` emits the credential_process JSON schema
        # (AccessKeyId/SecretAccessKey/SessionToken/…). There is no `json` format.
        proc = subprocess.run(
            ["aws", "configure", "export-credentials", "--format", "process"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        die(
            "aws CLI not found, and no AWS_ACCESS_KEY_ID in the environment.\n"
            "       Either set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or\n"
            "       install the CLI (brew install awscli) and configure a key."
        )
    except subprocess.CalledProcessError as exc:
        die(
            "could not resolve AWS credentials.\n"
            "       Put an access key in ~/.aws/credentials, or set\n"
            "       AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.\n"
            f"       aws said: {exc.stderr.strip()}"
        )
    data = json.loads(proc.stdout)
    return {
        "aws_access_key_id": data["AccessKeyId"],
        "aws_secret_access_key": data["SecretAccessKey"],
        "aws_session_token": data.get("SessionToken"),
    }


def session():
    """A boto3 Session carrying the bridged credentials.

    The credential bridge above is per-*session*, not per-service, so anything
    else in the package that needs an AWS client asks for one of these rather
    than repeating the `aws configure export-credentials` dance. `ddb.py` is the
    second caller; this module stays the one auth path for the whole package.
    """
    try:
        import boto3
    except ImportError:  # pragma: no cover - deps declared in entry scripts
        die("boto3 is not installed — run `uv sync` in studio/pipeline.")
    creds = _resolve_credentials()
    return boto3.session.Session(region_name=REGION, **(creds or {}))


def client():
    """A boto3 S3 client authenticated for the current AWS login/profile."""
    return session().client("s3")


# `list_keys` / `_list` and a re-export of `store.natural_key` lived here and
# are deleted. The listing helpers had one caller — the layout migrator, which
# is gone — and the re-export existed only to sort their results. Its comment
# already recorded a measurement: no caller imports `natural_key` from here,
# every one reaches `store.natural_key` directly, and that is still true. The
# one definition of the sort stays in `store.py`, which is the point the
# re-export was making.

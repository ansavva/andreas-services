# Shared helpers for the studio-media-s3 skill: credential resolution + a boto3 S3 client,
# plus bucket/prefix config and small utilities. Imported by s3_upload.py /
# s3_download.py / s3_presign.py — not run directly.
#
# Credentials: the Terraform provider and boto3's default chain do NOT understand
# the AWS CLI's `aws login` (login_session) credentials. The AWS CLI does, so we
# bridge them: `aws configure export-credentials` resolves whatever the CLI can
# (login_session / SSO / credential_process / static) into concrete keys, which
# we hand to boto3. Explicit AWS_ACCESS_KEY_ID in the environment wins and skips
# the bridge.
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
# The tree lives at the bucket ROOT. `media/` was a leftover from mirroring
# Google Drive 1:1 and bought nothing — the bucket is the media store. This
# stays as the single place a global prefix could be reintroduced (a shared
# bucket, a staging copy) without any other module learning about it.
PREFIX = os.environ.get("STUDIO_S3_PREFIX", "")
if PREFIX:
    PREFIX = PREFIX.strip("/") + "/"
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




def key(rel_path: str) -> str:
    """Turn a tree-relative path into a full S3 key.

    e.g. "characters/<name>/reference/face_01.png" -> the same, since PREFIX is
    empty by default. Build paths with `paths.py`, not by hand.
    """
    return PREFIX + rel_path.lstrip("/")


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
        die("aws CLI not found. Install it (brew install awscli) and run 'aws login'.")
    except subprocess.CalledProcessError as exc:
        die(
            "could not resolve AWS credentials via the aws CLI.\n"
            "       Run 'aws login' (or 'aws sso login' / 'aws configure') first.\n"
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


# Re-exported, not redefined: `store.natural_key` is the one definition, and two
# copies of a sort that decides which reference image a model is handed is
# exactly the drift worth avoiding.
#
# This comment used to claim "a dozen callers still import it from here". None
# do — every caller reaches `store.natural_key` directly, and the only use left
# is `_list` below. The re-export survives on the weaker ground that deleting it
# would break an import nobody has written yet for no gain; the count was
# measured, not the claim.
from studio_pipeline.adapters.store import natural_key  # noqa: E402,F401


def list_keys(s3, rel_prefix: str):
    """Object keys under <rel_prefix>/, excluding folder markers, natural-sorted."""
    return _list(s3, key(rel_prefix.rstrip("/") + "/"))


def _list(s3, prefix: str):
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue  # folder marker
            keys.append(key)
    keys.sort(key=natural_key)
    return keys

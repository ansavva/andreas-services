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
import re
import subprocess
import sys

# STUDIO_S3_*, not XHARNESS_S3_*. The bucket was renamed to
# `studio-prod-media-us-east-1` and the variables were renamed with it, which is
# load-bearing rather than tidiness: `dev-setup.sh` only writes the variable
# when it is absent, so every developer with an older `.env` carried a pinned
# `XHARNESS_S3_BUCKET=xharness-...` that would have quietly kept the pipeline
# writing to the archive after the cutover. Renaming the variable makes that
# stale line inert instead of silently wrong.
BUCKET = os.environ.get("STUDIO_S3_BUCKET", "studio-prod-media-us-east-1")
# The tree lives at the bucket ROOT. `media/` was a leftover from mirroring
# Google Drive 1:1 and bought nothing — the bucket is the media store. This
# stays as the single place a global prefix could be reintroduced (a shared
# bucket, a staging copy) without any other module learning about it.
PREFIX = os.environ.get("STUDIO_S3_PREFIX", "")
if PREFIX:
    PREFIX = PREFIX.strip("/") + "/"
# LEGACY: the pre-restructure prefix. Used only by the migrator, to recognise
# what has not been moved yet. It goes away once no bucket holds an old tree.
MEDIA_PREFIX = os.environ.get("STUDIO_S3_MEDIA_PREFIX", "media/").strip("/") + "/"
REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


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


_NUM_RE = re.compile(r"(\d+)")


def natural_key(s: str):
    """Sort key so <name>_2 < <name>_10 (lexical sort would flip them)."""
    return [int(t) if t.isdigit() else t.lower() for t in _NUM_RE.split(s)]


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

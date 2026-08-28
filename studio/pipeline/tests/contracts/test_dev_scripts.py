"""The dev-stack shell scripts, checked from the suite that actually runs.

`studio/scripts/` belongs to neither half of studio and has no suite of its own,
so it is checked here — the pipeline suite is the one CI runs for the local half,
and `studio-pr.yml`'s path filter names `studio/scripts/**` so a change to a
script runs these.

**Nothing here touches AWS.** Every test either reads a script's source or
sources it and calls a function that reads and writes nothing. The one thing
these cannot do is run `dev-aws-seed.sh` end to end: the fixture it loads is
#284, which is human-gated because it generates media, and the seed bucket does
not exist yet.
"""



import subprocess

from studio_pipeline import STUDIO_DIR
from tests.support.shell import SCRIPTS, SEED, SHARED, source_and_run

BUCKET = "studio-dev-abc123456789-media-us-east-1"


#: Re-exported so this module reads as it did. The implementation moved to
#: `tests/support/shell.py` when `unit/maintenance/test_dev_seed.py` needed it
#: too — see that module on why a test importing a test stopped working.
_source_and_run = source_and_run


def _code_lines(path) -> str:
    """A script with its comment lines removed.

    Whole-line comments only. A trailing comment on a command line stays, which
    is the conservative direction: this is used to look for things that must not
    be there, so keeping too much can only produce a false failure.
    """
    return "\n".join(line for line in path.read_text().splitlines()
                     if not line.lstrip().startswith("#"))


# ── the money pin ───────────────────────────────────────────────────────────
#
# #285: "This script must never be able to spend money. It does not generate. It
# does not call Replicate. It requires no REPLICATE_API_TOKEN. … That is a
# property worth pinning with a test rather than a comment: a setup script that
# can bill you is a bad setup script."




def test_no_dev_aws_script_names_the_provider_token():
    """The whole family, comments included — a token it cannot name it cannot read.

    Wider than the test above and weaker: it is one string. It is here because
    `dev-aws-setup.sh` calls into this family, so the property has to hold for
    more than the one script that would do the spending.
    """
    for script in sorted(SCRIPTS.glob("dev-aws-*.sh")):
        assert "REPLICATE_API_TOKEN" not in script.read_text(), script.name


def test_dev_aws_seed_destroys_nothing():
    """A seed converges a stack. Emptying one is `dev-aws-reset.sh`.

    Same shape of check and the same limits: it reads source, so it catches the
    line someone adds here and not a delete reached through something else.
    """
    code = _code_lines(SEED)
    for token in ("s3 rm", "s3 rb", "delete-object", "delete-table",
                  "delete-item", "admin-delete-user", "delete-user-pool",
                  "terraform destroy", "terraform apply"):
        assert token not in code, f"{SEED.name} runs {token!r}, which a seed must not"


def test_the_pose_plate_sync_can_never_delete():
    """`--delete` would remove whatever a fixture put under `config/`.

    The comment in `dev-shared-material.sh` says never; this is what makes it
    true after someone edits the line.
    """
    assert "--delete" not in _code_lines(SHARED)


# ── the ids, against the Python that derives them the same way ──────────────








# ── the items, against the schema itself ────────────────────────────────────
#
# **These used to compare the bash items attribute-for-attribute against
# `catalog_seed.meta_item` / `index_item`.** That Python twin is gone with the
# catalog seed, so the comparison would now be against nothing. What replaced it
# is an explicit statement of the schema — which is weaker in one way (two
# writers can no longer be diffed) and stronger in another: the expected item is
# written out here in full, so a reviewer can read what the loader writes
# without holding a second module in their head.
#
# The type mapping is still the thing most worth pinning. `size` as `{"S": …}`
# instead of `{"N": …}` is exactly the mistake a hand-written attribute map
# makes, and it makes a row that sorts and compares wrong rather than one that
# fails.






















# ── the fixture contract ────────────────────────────────────────────────────

# A version-2 fixture: entity roots are children of the LIBRARY root, so there
# is no `projects/` folder in the paths any more. A version-1 fixture would load
# a library holding two folders literally called `characters` and `projects`,
# owned by nobody — which is why the version moved rather than the shape being
# widened quietly.








# ── the shared material, with a stub in place of the AWS CLI ────────────────




def _push_plates(has_studio: bool) -> tuple[int, list[str]]:
    """Run `push_pose_plates` with a fake `studio` on PATH, and report its calls."""
    presence = "" if has_studio else "command() { return 1; }\n    "
    script = f"""
    set -euo pipefail
    fake_studio() {{
      printf '%s\\n' "$*" >&2
      return 0
    }}
    {presence}SHARED_MATERIAL_STUDIO=(fake_studio)
    source "{SHARED}"
    push_pose_plates "{STUDIO_DIR}" a-dev-bucket
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return result.returncode, result.stderr.splitlines()


def test_the_plates_are_pushed_through_the_cli_not_the_bucket():
    """**The push writes rows, so it cannot be an `aws s3 sync`.**

    `check_angles` resolves each plate as a name path, so a plate needs a node,
    and only the API writes one. This script pushed objects with `aws s3 sync`
    for as long as the plates were addressed by raw key; a stack provisioned
    that way after the entity model refused every shoot for want of a row, and
    named this script while doing it.
    """
    code, calls = _push_plates(has_studio=True)

    assert code == 0
    assert calls == ["config sync --apply --quiet"], calls
    assert not any("s3" in c for c in calls), calls


def test_a_missing_cli_is_not_a_failure():
    """`dev-setup.sh` runs from the SessionStart hook and must not fail a session.

    The same reasoning `config sync` applies to a missing sign-in: report and
    carry on, and let the first shoot name the real problem.
    """
    code, calls = _push_plates(has_studio=False)

    assert code == 0
    assert calls == [], calls




# ── the jq marshaller ───────────────────────────────────────────────────────










def test_the_seed_script_delegates_rather_than_reimplementing():
    """**It was a thousand lines and is now forty-nine.**

    The loader is `studio dev-seed load`, beside `publish`, so the two halves of
    a fixture share one set of derivations and one validator instead of being a
    bash implementation and a Python one held together by a contract test. What
    forced it was arithmetic: the shell version pulled 12.4 MB out of S3 and
    pushed it straight back, one `aws` process per object, and took 71 seconds
    to do about 0.6 seconds of work.

    What stays here is the part that cannot move — the angle images go in through
    the API, so they need a signed-in CLI and a library that already exists.
    """
    code = _code_lines(SEED)
    assert "studio dev-seed load" in code
    assert "push_pose_plates" in code
    assert len(SEED.read_text().splitlines()) < 100

    # None of the machinery it used to carry. Each of these was a real source of
    # bugs: uuid5 in bash, TSV rows that `read` collapsed, a one-level jq
    # marshaller that turned a nested bible into a string.
    for gone in ("uuid5_url", "derive_node_id", "blob_key_for", "fixture_problems",
                 "DDB_JQ_DEFS", "node_row_fixup", "IFS=$'\\t'"):
        assert gone not in code, f"{gone} should have moved to dev_seed.py"


def test_the_seed_script_still_runs_before_the_library_exists_is_not_a_thing():
    """The plate push comes AFTER the load, and that ordering was a real bug.

    `studio config sync` resolves through `GET /api/resolve`, which answers out
    of the caller's memberships — and the membership row is written by the load.
    Pushing first failed with "You are not a member of any library" on exactly
    the fresh stacks it was there to furnish.
    """
    code = _code_lines(SEED)
    assert code.index("studio dev-seed load") < code.index("push_pose_plates")

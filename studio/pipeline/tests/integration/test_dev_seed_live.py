"""`dev-seed` against the stack it was published from.

`tree` and `publish --dry-run` both read the real catalog table with boto3 —
these two commands are the only ones in the pipeline that open an AWS client of
their own, so the unit suite exercises them under moto and this is the only
place the real table answers.

**Nothing here passes `--apply`.** A dry run reads and reports; publishing would
overwrite `v1` in a bucket that has no `force_destroy` and is shared by every
machine.
"""
from __future__ import annotations


def test_the_tree_lists_the_seeded_character(studio, seeded):
    """The fixture loaded, and the tree is how a person checks that."""
    assert "jason" in seeded
    assert "jason/seed" in seeded


def test_the_tree_reports_the_stack_it_read(studio, seeded):
    """It names the bucket and the table before the listing, so a run against
    the wrong stack is visible in its own first two lines."""
    assert "studio-dev-" in seeded
    assert "prod" not in seeded


def test_a_dry_run_publish_reports_without_writing(studio, seeded):
    """The whole publisher short of the write: it reads the catalog, walks
    `parent_id` for every path, expands the selection, downloads the blobs and
    builds both documents.

    `--max-objects 60` because the fixture is 54 and the default cap is 12 —
    raised at the CALL SITE, never in code, so "refusing to publish everything"
    stays the default.
    """
    result = studio("dev-seed", "publish", "--path", "jason",
                    "--max-objects", "60")

    assert "Dry run" in result.stdout
    assert "--dev-subjects-only" in result.stdout
    assert "54" in result.stdout


def test_the_cap_refuses_a_selection_that_is_too_large(studio, seeded):
    """A folder brings its subtree, which is how a careful selection becomes a
    wholesale one by accident."""
    result = studio("dev-seed", "publish", "--path", "jason", check=False)

    assert result.returncode != 0
    assert "max-objects" in (result.stdout + result.stderr)


def test_a_selected_profile_beats_a_prod_bucket_in_the_environment(studio, seeded):
    """**Written expecting a refusal, and the truth is better than that.**

    `source()` does refuse a bucket with `prod` in the name — but it is never
    reached, because an explicitly selected profile wins over an exported
    `STUDIO_S3_BUCKET` and says so on stderr. That direction is deliberate:
    `dev-up.sh` exports those variables, and if one of them won, a `--profile`
    typed in that window would silently keep talking to the other stack.

    So the guard that actually protects this suite is the profile, and the
    refusal behind it is the second line. Asserting the real behaviour rather
    than the one this test was written to expect.
    """
    result = studio("dev-seed", "tree",
                    STUDIO_S3_BUCKET="studio-prod-media-us-east-1")

    noise = result.stdout + result.stderr
    assert "overrides $STUDIO_S3_BUCKET" in noise
    assert "studio-dev-" in result.stdout
    assert "studio-prod-media-us-east-1/" not in result.stdout


def test_the_shared_config_folder_does_not_block_a_publish(studio, seeded):
    """**The regression this tier existed for about ten minutes before finding.**

    The angle images are nodes under `config/`, and the loader creates them. The
    publisher checks every top-level folder against `DEV_SUBJECTS`, so a stack
    the loader had successfully seeded was refused over a folder the loader had
    just made. It had never fired because the plate push was broken.
    """
    result = studio("dev-seed", "publish", "--path", "jason",
                    "--max-objects", "60")

    assert "REFUSED" not in result.stdout
    assert "Dry run" in result.stdout

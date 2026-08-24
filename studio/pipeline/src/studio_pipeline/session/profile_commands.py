"""`studio profile` — list, inspect, choose and refresh the named environments.

Where `commands.py` answers "who am I", this answers "where am I pointing". The
two are one question in practice, which is why `whoami` prints the profile and
this prints whether each profile has a session.

**Nothing here is typed by hand.** `sync` reads a stack's real values — dev from
its Terraform state object, prod from the SSM parameters the deploy workflow
writes — so a profile cannot describe a stack that does not exist, and no id
ever has to be copied into a file by a person. That is the same argument
`dev-setup.sh` makes for reading dev's values from Terraform rather than SSM:
nothing deploys a dev stack, and nothing but the deploy writes prod's.

The rules the resolution follows are in `studio_pipeline/profiles.py`.
"""

from __future__ import annotations

import click

from studio_pipeline import profiles
from studio_pipeline.adapters import auth


@click.group("profile")
def main() -> None:
    """Named environments: which stack the CLI talks to."""


@main.command("list")
def cmd_list() -> None:
    """Every profile, with the one in force marked `*`."""
    names = profiles.names()
    if not names:
        click.echo("No profiles yet. Create them with:")
        click.echo("  studio profile sync dev     # this machine's dev stack")
        click.echo("  studio profile sync prod    # the deployed library")
        return

    in_force = profiles.current()
    signed_in = auth.sessions()
    width = max(len(n) for n in names)
    for name in names:
        fields = profiles.fields(name)
        mark = "*" if name == in_force else " "
        session = "signed in" if name in signed_in else "—"
        click.echo(
            f"{mark} {name:<{width}}  {fields.get('api_url', '(no api_url)'):<40}"
            f"  {session}"
        )
    if in_force not in names:
        # A `use`d or `--profile`d name with no section is the one case the
        # listing cannot show as a row, and it is exactly the case that produces
        # a confusing "does not define api_url" three commands later.
        click.echo(f"\nnote: the profile in force is {in_force!r}, which has no entry above.")


@main.command("show")
@click.argument("name", required=False)
def cmd_show(name: str | None) -> None:
    """What each field resolves to, and what supplied it.

    Without NAME, the profile in force and its real sources — so an exported
    variable shows up as `$STUDIO_API_URL` rather than being invisible. With
    NAME, that profile as if it had been selected explicitly.
    """
    target = name or profiles.current()
    click.echo(f"profile  {target}")
    if name and not profiles.exists(name):
        raise click.ClickException(
            f"No profile named {name!r}. Create it with: studio profile sync {name}"
        )
    rows = profiles.describe(name)
    width = max(len(field) for field, _, _ in rows)
    for field, value, source in rows:
        click.echo(f"{field:<{width}}  {value or '(unset)':<44}  {source}")
    source = profiles.fields(target).get("source")
    if source:
        click.echo(f"{'synced from':<{width}}  {source}")
    click.echo(f"{'session':<{width}}  "
               f"{'signed in' if target in auth.sessions() else 'not signed in'}")


@main.command("use")
@click.argument("name")
def cmd_use(name: str) -> None:
    """Make NAME the profile used when neither --profile nor STUDIO_PROFILE is given."""
    try:
        profiles.set_current(name)
    except profiles.ProfileError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Default profile is now {name}.")
    click.echo("Per-invocation, this is still: studio --profile <name> <command>")


@main.command("sync")
@click.argument("name")
@click.option("--api-url", default=None,
              help="Override the API this profile points at. Only meaningful for "
                   "dev, whose API is whatever dev-up.sh is serving.")
def cmd_sync(name: str, api_url: str | None) -> None:
    """Refresh NAME's fields from the stack it names. Needs AWS credentials.

    `dev` reads this machine's Terraform state; `prod` reads /studio/prod/* from
    SSM. Any other name has no known source and must be written by hand.
    """
    syncer = profiles.SYNCERS.get(name)
    if syncer is None:
        raise click.ClickException(
            f"No sync source is defined for {name!r}. "
            f"Known: {', '.join(sorted(profiles.SYNCERS))}."
        )
    try:
        values = syncer(api_url=api_url) if name == "dev" and api_url else syncer()
    except profiles.ProfileError as error:
        raise click.ClickException(str(error)) from error

    profiles.save(name, values)
    click.echo(f"Synced profile {name} from {values['source']}:")
    for field in profiles.FIELDS:
        click.echo(f"  {field:<22} {values[field]}")

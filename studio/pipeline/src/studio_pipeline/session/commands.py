"""`studio login` / `logout` / `whoami` — the CLI's session (#300).

Three commands and no more. Signing in is the whole of what they do; everything
else the CLI knows about identity it reads back off the stored token. Where the
session points is `profile_commands.py` next door — a session belongs to a
profile, so both of these name it in their output.

**The acceptance test for the whole epic is that these work on a machine with no
AWS credentials configured at all.** That is why `adapters/auth` builds an
unsigned Cognito client: `InitiateAuth` needs no AWS identity, but boto3 resolves
the credential chain at client construction and would fail first.
"""

from __future__ import annotations

import datetime as dt
import os

import click

from studio_pipeline import profiles
from studio_pipeline.adapters import api, auth


@click.command("login")
@click.option("--email", help="The account to sign in as. Prompted for if omitted.")
def cmd_login(email: str | None) -> None:
    """Sign in to studio and store the session."""
    email = email or click.prompt("Email")
    # `hide_input`, and never an `--password` option: an argument is visible in
    # `ps` to every other process on the machine, and in the shell history
    # afterwards.
    password = os.environ.get("STUDIO_PASSWORD") or click.prompt("Password", hide_input=True)
    try:
        body = auth.login(email, password)
    except auth.AuthError as error:
        raise click.ClickException(str(error)) from error

    # **Naming the profile is not decoration.** There is one credentials store
    # per machine and `login` writes into whichever profile is in force, so a
    # sign-in that did not say which one is a sign-in you cannot check.
    click.echo(f"Signed in as {body.get('email', email)} on profile {profiles.current()}.")
    _show_libraries()


@click.command("logout")
def cmd_logout() -> None:
    """Forget the stored session."""
    if auth.logout():
        click.echo("Signed out.")
    else:
        click.echo("Not signed in.")


@click.command("whoami")
def cmd_whoami() -> None:
    """Show who is signed in, and which libraries they can reach."""
    try:
        who = auth.whoami()
    except auth.AuthError as error:
        raise click.ClickException(str(error)) from error

    # First, because it is the line that decides what the other four mean.
    click.echo(f"profile  {who['profile']}")
    click.echo(f"email    {who['email']}")
    click.echo(f"sub      {who['sub']}")
    click.echo(f"pool     {who['pool']}")
    click.echo(f"api      {who['api_url']}")
    if who.get("expires_at"):
        expires = dt.datetime.fromtimestamp(who["expires_at"], dt.timezone.utc)
        click.echo(f"expires  {expires.isoformat()}")
    _show_libraries()


def _show_libraries() -> None:
    """The libraries this session can reach, or why that could not be answered.

    **A failure here is reported, not raised.** `whoami` answering "who am I"
    correctly and "what can I reach" not at all is more useful than an exception
    that suppresses both — and the API being unreachable is exactly when someone
    runs `whoami`.
    """
    try:
        found = api.libraries()
    except (api.ApiError, auth.AuthError) as error:
        click.echo(f"library  (could not reach the API: {error})")
        return
    if not found:
        # The provisioning gap the API's own 200-and-empty-list exists to make
        # visible: an account somebody created and never added to a library.
        click.echo("library  none — this account is in no library yet")
        return
    for entry in found:
        click.echo(f"library  {entry.get('name', '?')}  ({entry.get('id', '?')}, {entry.get('role', '?')})")

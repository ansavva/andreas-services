"""`studio signup` / `login` / `logout` / `whoami` — the CLI's session.

Four commands and no more. Getting an account and signing in to it is the whole
of what they do; everything else the CLI knows about identity it reads back off
the stored token. Where the
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


@click.command("signup")
@click.option("--email", help="The address to register. Prompted for if omitted.")
@click.option(
    "--library",
    "library_name",
    help="What to call the library the account starts with. Prompted for if omitted.",
)
@click.option(
    "--resume",
    is_flag=True,
    help="The account exists but was never confirmed: send a fresh code and pick up from there.",
)
def cmd_signup(email: str | None, library_name: str | None, resume: bool) -> None:
    """Create an account, confirm it, sign in, and make its first library.

    Four steps in one command because none of them is useful alone: an
    unconfirmed account cannot sign in, and a confirmed one in no library can
    reach nothing. The invite code comes from STUDIO_INVITE_CODE or a prompt;
    the password from STUDIO_PASSWORD or a prompt, never an option.
    """
    email = (email or click.prompt("Email")).strip()

    if not resume:
        password = os.environ.get("STUDIO_PASSWORD") or click.prompt(
            "Password (12+ characters, upper, lower, digit)",
            hide_input=True,
            confirmation_prompt=True,
        )
        invite = os.environ.get("STUDIO_INVITE_CODE") or click.prompt("Invite code", hide_input=True)
        try:
            destination = auth.sign_up(email, password, invite)
        except auth.AuthError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"A confirmation code has been sent to {destination}.")
    else:
        password = os.environ.get("STUDIO_PASSWORD") or click.prompt("Password", hide_input=True)
        try:
            auth.resend_confirmation(email)
        except auth.AuthError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"A fresh confirmation code has been sent to {email}.")

    code = click.prompt("Confirmation code")
    try:
        auth.confirm_sign_up(email, code)
        body = auth.login(email, password)
    except auth.AuthError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Signed in as {body.get('email', email)} on profile {profiles.current()}.")

    # The account is now real and can sign in, so from here a failure is
    # recoverable by `studio login` and a second try at the library — which is
    # why the library comes last rather than first.
    library_name = (
        library_name or click.prompt("Library name", default=_default_library(email))
    ).strip()
    try:
        created = api.create_library(library_name)
    except api.ApiError as error:
        raise click.ClickException(
            f"Signed in, but could not create the library: {error}. "
            "Run `studio whoami` and try again."
        ) from error
    click.echo(f"library  {created.get('name', library_name)}  ({created.get('id', '?')}, owner)")


def _default_library(email: str) -> str:
    """`ada@example.com` → `ada's library`. A name to accept, not to admire."""
    local = email.split("@", 1)[0] or "my"
    return f"{local}'s library"


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

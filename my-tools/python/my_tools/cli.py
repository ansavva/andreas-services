"""my-tools — unified personal toolbox CLI."""
import typer
from my_tools.photos import commands as photos_commands
from my_tools.media import commands as media_commands
from my_tools.qr import commands as qr_commands

app = typer.Typer(
    name="my-tools",
    help="Unified personal toolbox. Run `my-tools <group> --help` for details.",
    no_args_is_help=True,
)

# Register groups — adding a new group: create my_tools/<group>/commands.py with a
# `app = typer.Typer(...)`, then add one app.add_typer() line below.
app.add_typer(photos_commands.app, name="photos")
app.add_typer(media_commands.app, name="media")
app.add_typer(qr_commands.app, name="qr")

if __name__ == "__main__":
    app()

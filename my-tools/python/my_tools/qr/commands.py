"""QR group — QR code generation."""
from pathlib import Path
import typer

app = typer.Typer(
    help="QR code tools.",
    no_args_is_help=True,
)


@app.command("generate")
def generate(
    url: str = typer.Argument(..., help="URL to encode as a QR code"),
    output: Path = typer.Option(Path("qr_code.png"), "--output", "-o", help="Output PNG file path"),
    box_size: int = typer.Option(10, "--box-size", help="Pixel size per QR module"),
    border: int = typer.Option(4, "--border", help="Border width in QR modules"),
):
    """Convert a URL to a QR code PNG image."""
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(output))
    typer.echo(f"QR code saved to {output}")

from conftest import run_cli


def test_cli_help():
    rc, out, _ = run_cli("--help")
    assert rc == 0
    assert "photos" in out
    assert "media" in out
    assert "qr" in out


def test_photos_help():
    rc, out, _ = run_cli("photos", "--help")
    assert rc == 0
    assert "scan-takeout" in out
    assert "scan-icloud" in out
    assert "setup" in out


def test_media_help():
    rc, out, _ = run_cli("media", "--help")
    assert rc == 0
    assert "kindle" in out


def test_qr_help():
    rc, out, _ = run_cli("qr", "--help")
    assert rc == 0
    assert "generate" in out

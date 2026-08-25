"""Move a character's references from studio S3 onto the pod.

The path is presigned-GET pull: `studio character selection <slug> --presign
--json` mints the URLs (the API signs them; the lab holds no cloud
credentials, same as the pipeline), they land in urls.json, and the pod curls
them. The 900s TTL means mint and pull run back-to-back — this module does
both in one command for that reason.

The plaintext photos exist in exactly three places afterwards: studio S3,
the pod's /workspace/dataset/subject/, and nowhere on this machine.
"""

import json
import subprocess

import click

from lora_lab import LOCAL_DIR, studio_bin
from lora_lab.adapters import shell
from lora_lab.domain import pod

REMOTE_SUBJECT_DIR = "/workspace/dataset/subject"


def slug_dir(slug: str):
    d = LOCAL_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def mint_urls(slug: str) -> list[str]:
    """Shell out to the studio CLI — the same contract the skills use.

    Requires a live `studio login` against the stack that holds the character
    (for this experiment: prod, via scripts/prod-login.sh).
    """
    proc = subprocess.run(
        [studio_bin(), "character", "selection", slug, "--presign", "--json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise click.ClickException(
            f"`studio character selection {slug} --presign` failed:\n{proc.stderr.strip()}"
        )
    urls = json.loads(proc.stdout)
    if not isinstance(urls, list) or not urls:
        raise click.ClickException(f"no reference URLs came back for {slug}")
    return urls


def push_refs(slug: str) -> None:
    ip, port = pod.endpoint()
    urls = mint_urls(slug)
    click.echo(f"presigned {len(urls)} reference image(s); pulling onto the pod…")

    urls_file = slug_dir(slug) / "urls.json"
    urls_file.write_text(json.dumps(urls, indent=2))
    shell.run(ip, port, f"mkdir -p {REMOTE_SUBJECT_DIR}")
    shell.scp_to(ip, port, urls_file, f"{REMOTE_SUBJECT_DIR}/urls.json")
    # Pull with indexed names; the URLs expire on their own, but remove the
    # file anyway — it has no later use and it reads like a secret.
    shell.run(
        ip, port,
        "cd %s && python3 -c \""
        "import json,urllib.request;"
        "urls=json.load(open('urls.json'));"
        "[open(f'ref-{i:02d}.png','wb').write(urllib.request.urlopen(u).read())"
        " for i,u in enumerate(urls)];"
        "print(f'{len(urls)} pulled')\" && rm -f urls.json && ls -la" % REMOTE_SUBJECT_DIR,
        stream=True,
    )
    urls_file.unlink()
    click.echo("references are on the pod (and the local urls.json is gone).")

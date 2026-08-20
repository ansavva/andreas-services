"""`studio backfill-replicate` — import historical Replicate predictions into the run store.

One-shot recovery tool for predictions made before the run store existed. It reads
the Replicate predictions API and writes a run per prediction under
`projects/<project>/runs/`, so the history is uniform with everything recorded going
forward.

WHAT IT CAN AND CANNOT RECOVER
------------------------------
Replicate purges prediction inputs and outputs after a retention window and flags
the record `data_removed: true`. For those, the prompt and the artifact are simply
GONE — this tool records what genuinely survives (model, status, timings, error,
metrics) and marks the run `data_removed: true`. It NEVER invents a prompt, and it
never guesses a project: with no inputs there are no S3 paths to attribute from, so
purged runs land in the `misc` project rather than being mis-filed under a
character.

Where inputs DO survive, any URL-bearing field is recorded under
`external_inputs` rather than `bindings`, because those URLs point outside our
bucket (e.g. Replicate's own file API) and are not S3 keys. `bindings` stays
reserved for real S3 keys, so the storage invariant holds.

  studio backfill-replicate --since 2026-08-01 --dry-run
  studio backfill-replicate --since 2026-08-01

Idempotent: a prediction whose run already exists is skipped, so it is safe to
re-run.

It writes through `domain/runs.py` and holds no AWS client of its own, so since
#304 it reaches the store through the API like every other run writer. That is
not the same call as the rest of `maintenance/`: `catalog_seed.py` and
`migrate_layout.py` enumerate the raw bucket and keep boto3 deliberately,
because applying the prefix at the AWS boundary is the job. This one only
records runs.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import click

from studio_pipeline import env_value
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import registry as REG

UA = "xharness-studio/1.0"
API = "https://api.replicate.com/v1/predictions"


def classify(model: str) -> tuple[str, str, str]:
    """(owning skill, medium, filename slug) for a Replicate model id.

    Read from the model registry rather than a local table, so a model added
    with `studio-media-add-model` is importable by the backfill immediately.
    """
    entry = REG.by_model_id(model)
    if not entry:
        return ("(unknown)", "unknown", "run")
    return (entry["skill"], entry["kind"], entry.get("backfill_slug", entry["key"]))


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_token() -> str:
    tok = os.environ.get("REPLICATE_API_TOKEN")
    if tok:
        return tok.strip()
    tok = env_value("REPLICATE_API_TOKEN")
    if tok:
        return tok
    die("REPLICATE_API_TOKEN not set (environment or studio/.env).")


def api(url: str, token: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req) as r:
        # Replicate's `logs` field can carry raw control characters.
        return json.loads(r.read().decode(), strict=False)


def download(url: str, local: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req) as r, open(local, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return local


def split_urls(inp: dict) -> tuple[dict, dict]:
    """Separate plain inputs from URL-bearing ones (which are NOT S3 keys)."""
    plain, external = {}, {}
    for k, v in (inp or {}).items():
        vals = v if isinstance(v, list) else [v]
        if any(isinstance(u, str) and u.startswith("http") for u in vals):
            external[k] = v
        else:
            plain[k] = v
    return plain, external


def run_id_for(pred: dict, slug_hint: str) -> str:
    created = (pred.get("created_at") or "")[:19].replace("T", "_")
    ts = created.replace(":", "-") or dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}_{R.slugify(slug_hint)}"


@click.command(help=__doc__)
@click.option("--dry-run", is_flag=True, help="Report what would be written; write nothing.")
@click.option("--max-pages", type=int, default=50)
@click.option("--project", default='misc', help="Project for imported runs (default: misc).")
@click.option("--since", required=True, help="ISO date, e.g. 2026-08-01 (inclusive).")
@click.option("--until", help="ISO date, exclusive upper bound.")
def backfill_replicate(dry_run, max_pages, project, since, until):
    token = load_token()

    # --- collect predictions in range -------------------------------------
    url, preds, pages = API, [], 0
    while url and pages < max_pages:
        page = api(url, token)
        preds += page.get("results", [])
        pages += 1
        if preds and min((p.get("created_at") or "") for p in preds) < since:
            break
        url = page.get("next")
    sel = [p for p in preds if (p.get("created_at") or "") >= since
           and (not until or (p.get("created_at") or "") < until)]
    sel.sort(key=lambda p: p.get("created_at") or "")
    print(f"{len(sel)} prediction(s) in range (from {len(preds)} scanned)", file=sys.stderr)

    stats = {"written": 0, "skipped": 0, "purged": 0, "with_output": 0, "failed_download": 0}
    for p in sel:
        pid = p["id"]
        full = api(f"{API}/{pid}", token)  # list results are abbreviated
        model = full.get("model") or "unknown"
        engine, kind, short = classify(model)
        rid = run_id_for(full, f"{short}-{pid[:8]}")
        purged = bool(full.get("data_removed"))
        if purged:
            stats["purged"] += 1

        if R.read_json(R.run_key(project, rid, "request.json")) is not None:
            stats["skipped"] += 1
            continue

        plain, external = split_urls(full.get("input") or {})
        out = full.get("output")
        out_urls = [out] if isinstance(out, str) else list(out or [])

        if dry_run:
            print(f"  would write {project}/{rid}  {model} {full.get('status')}"
                  f"{' [data_removed]' if purged else ''}"
                  f"{f' +{len(out_urls)} output' if out_urls else ''}")
            stats["written"] += 1
            continue

        R.record_request(
            project, rid, kind=kind, engine=engine, model=model,
            input=plain, bindings={},
            extra={
                "backfilled": True,
                "backfill_source": "replicate predictions API",
                "prediction_id": pid,
                "submitted_at": full.get("created_at"),
                # URLs that are NOT S3 keys, so they cannot be bindings.
                "external_inputs": external or None,
                "data_removed": purged,
                "note": ("Replicate purged this prediction's input/output; the prompt "
                         "is unrecoverable and was NOT reconstructed."
                         if purged else None),
            },
        )

        out_keys = []
        if out_urls:
            stats["with_output"] += 1
            staged = tempfile.mkdtemp(prefix="backfill-")
            for i, u in enumerate(out_urls, start=1):
                ext = os.path.splitext(urllib.parse.urlparse(u).path)[1] or ".bin"
                base = f"{short}-{pid[:8]}{'' if len(out_urls) == 1 else f'-{i}'}{ext}"
                try:
                    local = download(u, os.path.join(staged, base))
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    print(f"  {rid}: output no longer fetchable ({e})", file=sys.stderr)
                    stats["failed_download"] += 1
                    continue
                out_keys.append(R.upload_output(project, rid, local, base))
                os.remove(local)

        R.record_result(
            project, rid, prediction_id=pid, status=full.get("status") or "unknown",
            outputs=out_keys, source_urls=out_urls, error=full.get("error"),
            extra={
                "backfilled": True,
                "data_removed": purged,
                "metrics": full.get("metrics"),
                "started_at": full.get("started_at"),
                "replicate_completed_at": full.get("completed_at"),
                "output_archived": bool(out_keys),
            },
        )
        stats["written"] += 1
        print(f"  {project}/{rid}  {model} {full.get('status')}"
              f"{' [data_removed]' if purged else ''}"
              f"{f' +{len(out_keys)} archived' if out_keys else ''}", file=sys.stderr)

    print(json.dumps(stats, indent=2))
    return 0

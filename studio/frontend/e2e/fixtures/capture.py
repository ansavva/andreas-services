#!/usr/bin/env python3
"""Re-capture the e2e fixtures off the real API.

    studio/scripts/dev-up.sh                 # the API, on :8000
    python studio/frontend/e2e/fixtures/capture.py            # both groups
    python studio/frontend/e2e/fixtures/capture.py --seed     # the seed group
    python studio/frontend/e2e/fixtures/capture.py --runs     # the authoring group

TWO GROUPS, AND NO ONE STACK IS RIGHT FOR BOTH
-----------------------------------------------
The **seed** group (`libraries`, `characters`, `character`, `character-root`,
`seed-folder`, `projects`, `reel`) is a portrait of the PUBLISHED dev-seed
fixture — the 54-object character every developer's stack loads and nothing
else. `browse.spec.ts` asserts against those numbers deliberately: the "49 jpeg
and 5 png" spec is the record of why the seed images were normalised at all.
Taking them off a stack somebody has since worked in replaces that with a
snapshot of one developer's afternoon, and the assertions become arbitrary.
**Re-take these on a freshly seeded stack only.**

The **authoring** group (everything from `project` down) is the opposite: it
needs a stack that HAS been worked in, because the seed holds no project, no
runs and nothing submitted — see below.

So a bare run does both and the second half will refuse, loudly, on a fresh
stack. That is the two groups disagreeing about which stack they want, said out
loud rather than quietly writing one of them wrong.

**The fixtures are captured, not written.** A hand-written stub drifts from the
API silently and then asserts its own imagination; one taken from the thing it
stands in for cannot drift without somebody re-running this.

SCRUBBING IS NOT OPTIONAL AND IT IS WHY THIS IS A SCRIPT
--------------------------------------------------------
`GET /api/nodes` answers with PRESIGNED S3 URLs, and a presigned URL carries the
signing key's ACCESS KEY ID in `X-Amz-Credential` along with a signature. Those
are not things to commit, and a `curl > fixture.json` puts them straight into
git — which is exactly what the first capture did. The signature expires in
fifteen minutes; the key id does not.

They also break the run. The browser fetches those URLs directly, so a "stubbed"
suite quietly reached real S3 for fourteen images — caught by the spec that
asserts nothing escapes to the network, which is the whole reason that spec is
there.

Every URL becomes `/e2e-asset.png`, which `support/api.ts` answers with a real
one-pixel PNG — or `/e2e-asset.mp4` when the key it signed was a clip, because a
`<video>` handed PNG bytes fires `error` and draws "this file could not be
loaded", which is a screen that proves nothing about the thing being tested.

WHAT THE RUN-AUTHORING FIXTURES NEED, AND WHY THEY ARE NOT THE SEED
-------------------------------------------------------------------
The published dev seed is one character and 54 stills. It holds no project, no
runs and nothing that has ever been submitted — so the three screens the run
specs are about (a project's Runs tab, a draft in the editor, a finished run
with an output to promote) cannot be captured from a freshly seeded stack. They
come from a stack that has been WORKED IN: a project with a draft and a
succeeded image run in it.

Which ones are picked is discovery, not a hard-coded id — the first project, its
newest draft, its newest succeeded image run — so a second machine's stack
answers the same script. `STUDIO_E2E_PROJECT` and `STUDIO_E2E_SCHEMA_MODEL`
override the two choices worth steering.

THIS SCRIPT WRITES, IN EXACTLY ONE PLACE
-----------------------------------------
`created-run.json` is the 201 body of `POST /api/runs`, and there is no way to
capture the shape of a creation without creating something. So it creates a
draft and then deletes it again (`?files=delete`). A draft costs nothing and
sends nothing — `submit` is the call that spends, and this never makes it. If
the delete fails, the stack is left holding one abandoned draft; the script says
so rather than hiding it.

ONE FIXTURE IS SYNTHESISED, AND IT IS STILL NOT FETCHED
-------------------------------------------------------
`e2e-asset.mp4` is generated here by ffmpeg rather than captured, because there
is nothing to capture it from: the published dev seed is 54 stills, since runs,
scenes and movies are model output and cost money to make. A `<video>` handed
the one-pixel PNG cannot play, which is the whole reason `browse.spec.ts` never
visited `/o`. Synthesising it locally keeps the rule the rest of this file is
about — nothing here reaches out to the internet for a sample clip.

    python capture.py --video     # just the MP4; needs no API and no token
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
STUDIO = HERE.parents[2]
API = os.environ.get("STUDIO_E2E_API", "http://localhost:8000")

#: The project to take the run fixtures from — a slug or an id. The first one
#: the library holds, when nothing says otherwise.
PROJECT = os.environ.get("STUDIO_E2E_PROJECT")
#: Whose live input schema `SchemaParams` is exercised against.
SCHEMA_MODEL = os.environ.get("STUDIO_E2E_SCHEMA_MODEL", "openai/gpt-image-2")

#: Anything that looks like a signed URL, wherever it appears.
SIGNED = re.compile(r"https?://[^\"\s]*X-Amz-(Signature|Credential)[^\"\s]*")
PLACEHOLDER = "/e2e-asset.png"
PLACEHOLDER_VIDEO = "/e2e-asset.mp4"

#: A clip, judged by the key that was signed rather than by a `content_type`
#: sitting beside it — a thumbnail URL arrives on its own, with no such sibling.
CLIP_KEY = re.compile(r"\.(mp4|mov|webm|m4v)$", re.IGNORECASE)

#: What must never survive `scrub`, checked on the way to disk.
#:
#: The signed URL is the one that already happened. The other two are the shapes
#: a NEW route could leak: a bare access key id (`AKIA…` long-lived, `ASIA…`
#: from an assumed role) and a JWT, which is what every request here carries in
#: its own Authorization header and is therefore one careless echo away.
LEAKS = (
    ("a signed URL", SIGNED),
    ("an AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
)


def placeholder_for(url: str) -> str:
    """Which of the two local assets stands in for this signed URL."""
    path = urllib.parse.urlsplit(url).path
    return PLACEHOLDER_VIDEO if CLIP_KEY.search(path) else PLACEHOLDER


def scrub(value):
    """Every presigned URL replaced, at any depth."""
    if isinstance(value, str):
        return placeholder_for(value) if SIGNED.match(value) else value
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    return value


def token() -> str:
    result = subprocess.run(  # noqa: S603 — a script this repo owns
        [str(STUDIO / "scripts" / "dev-token.sh"), "--no-prompt"],
        capture_output=True, text=True, check=True, timeout=180,
    )
    return result.stdout.strip()


def call(method: str, path: str, bearer: str, library: str | None, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{API}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {bearer}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if library:
        request.add_header("X-Studio-Library", library)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def get(path: str, bearer: str, library: str | None):
    return call("GET", path, bearer, library)


def write(name: str, body):
    cleaned = scrub(body)
    serialized = json.dumps(cleaned)
    for what, pattern in LEAKS:
        found = pattern.search(serialized)
        assert not found, f"{name} still holds {what}: {found.group()[:80]}"
    (HERE / f"{name}.json").write_text(json.dumps(cleaned, indent=2) + "\n")
    print(f"  {name}.json")
    return cleaned


#: Five seconds of one colour at 64x36 — 16:9 at the smallest size that is still
#: recognisably a frame, and long enough that `currentTime` visibly moves under a
#: test and the poster's duration badge has something to say. H.264 baseline,
#: because that is what Playwright's bundled Chromium decodes.
#:
#: Three flags are about what lands in git rather than about the picture.
#: `bitexact` drops the ffmpeg version stamp, so the same build re-runs to the
#: same bytes instead of to a diff. `filter_units` drops SEI NAL units, which is
#: where x264 writes its own version banner and command line — a committed binary
#: should be frames and nothing else. `faststart` puts the index first, so a
#: fulfilled 200 with no range support is enough to play it.
FFMPEG = [
    "ffmpeg", "-y", "-v", "error",
    "-fflags", "+bitexact",
    "-f", "lavfi", "-i", "color=c=0x1f1f1f:s=64x36:r=12:d=5",
    "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
    "-pix_fmt", "yuv420p", "-g", "12",
    "-bsf:v", "filter_units=remove_types=6",
    "-flags:v", "+bitexact", "-fflags", "+bitexact", "-movflags", "+faststart",
]


def video() -> None:
    """The one fixture that is made rather than taken. See the header."""
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not on PATH; `brew install ffmpeg`")
    out = HERE / "e2e-asset.mp4"
    subprocess.run([*FFMPEG, str(out)], check=True, timeout=120)  # noqa: S603
    print(f"  {out.name} ({out.stat().st_size} bytes)")


def model_path(name: str) -> str:
    """A model name as a path, quoted PER SEGMENT.

    `apis/studio.ts` does the same thing and for the same reason: a Replicate id
    is `owner/name`, the routes take a `<path:name>`, and quoting the whole
    string turns that slash into `%2F` — which Werkzeug's path converter does not
    match, so the request 404s on a model that exists.
    """
    return "/".join(urllib.parse.quote(part, safe="") for part in name.split("/"))


def newest(runs, **fields):
    """The first run matching every field. The listing is newest-first."""
    return next(
        (run for run in runs if all(run.get(key) == value for key, value in fields.items())),
        None,
    )


def authoring(bearer: str, library: str, character: dict) -> None:
    """The fixtures the run specs need, off a stack that has been worked in.

    Nothing here comes from the published seed — see the header. What it takes is
    one project, its runs listing WITH DRAFTS (the listing route hides them
    otherwise, so a draft would be invisible in the fixture the same way it was
    invisible in the app), one draft, one succeeded image run, the model registry
    and one live schema, and the two folder listings a promotion walks.
    """
    projects = get("/api/projects", bearer, library)
    wanted = PROJECT
    project_row = next(
        (row for row in projects if wanted in (row["id"], row["slug"])), None
    ) if wanted else (projects[0] if projects else None)
    if project_row is None:
        raise SystemExit(
            "no project to capture from. The authoring fixtures need a stack "
            "that has been worked in; a freshly seeded one holds no project at "
            "all. Re-take the seed group on its own with `--seed`."
        )
    project = write("project", get(f"/api/projects/{project_row['id']}", bearer, library))

    listing = get(
        f"/api/runs?project={project['id']}&include=drafts", bearer, library
    )
    write("project-runs", listing)
    runs = listing["runs"]

    draft = newest(runs, status="draft")
    done = newest(runs, status="succeeded", kind="image")
    if draft is None or done is None:
        raise SystemExit(
            "the project needs both a draft and a succeeded IMAGE run: the specs "
            "are about authoring one and promoting the other's output"
        )
    write("run-draft", get(f"/api/runs/{draft['id']}", bearer, library))
    write("run-image", get(f"/api/runs/{done['id']}", bearer, library))

    registry = write("models", get("/api/models", bearer, library))
    # Live — this one is a round trip to the provider, so it is the slowest call
    # in the script and the only one that can fail for reasons outside the stack.
    write("model-schema", get(f"/api/models/{model_path(SCHEMA_MODEL)}/schema", bearer, library))
    entry = next(
        each for each in registry["models"].values() if each["model"] == SCHEMA_MODEL
    )

    write("references", get(
        f"/api/characters/{character['id']}/references", bearer, library
    ))
    # The two listings `promoteToReference` walks on its way to a group folder:
    # the character's own root, then the `reference` pool inside it.
    tree = write(
        "character-tree",
        get(f"/api/nodes?under={character['root']}&sort=name", bearer, library),
    )
    # One array, discriminated by `kind` — `folders` and `files` stopped being
    # separate fields when the three listing routes became one.
    pool = next(e for e in tree["entries"]
                if e["kind"] == "folder" and e["name"] == "reference")
    write("reference-tree",
          get(f"/api/nodes?under={pool['id']}&sort=name", bearer, library))

    created(bearer, library, project["id"], entry)


def created(bearer: str, library: str, project: str, entry: dict) -> None:
    """A draft, made and then unmade — **the one thing this script writes.**

    Two fixtures come out of it, and the second is why the write is worth making
    rather than overriding a few fields on an existing draft by hand:

    - `created-run` is the 201 body, which is **not** a run envelope. It carries
      the handful of values the caller could not have known — the id, the
      `plan_digest` the next call approves against, the fingerprint — and
      nothing else.
    - `created-run-record` is `GET /api/runs/<id>` on that same draft, which is
      what the app reads the moment it navigates to the run it just made.

    A draft sends nothing and bills nothing; `submit` is the call that spends and
    this never makes it. Deleted again immediately, folder and all.
    """
    body = {
        "project": project,
        "kind": entry["kind"],
        "model": entry["model"],
        "engine": entry["skill"],
        # What `seedPlan` builds for a model with no snapshot defaults: the
        # smallest legal plan, which is what the editor then fills in.
        "plan": {"version": 1, "origin": "authored", "prompt": "", "params": {}},
    }
    record = call("POST", "/api/runs", bearer, library, body)
    try:
        write("created-run", record)
        write(
            "created-run-record",
            get(f"/api/runs/{record['id']}", bearer, library),
        )
    finally:
        try:
            call("DELETE", f"/api/runs/{record['id']}?files=delete", bearer, library)
            print(f"  (created and deleted {record['id']})")
        except urllib.error.HTTPError as failure:
            print(
                f"  WARNING: {record['id']} was created and NOT deleted "
                f"({failure.code}) — remove it with `studio runs delete`"
            )


def seed_group(bearer: str, library: str) -> dict:
    """The published seed, as the API describes it. See the header."""
    libraries = get("/api/libraries", bearer, None)
    write("libraries", libraries)

    characters = get("/api/characters", bearer, library)
    write("characters", characters)
    character = get(f"/api/characters/{characters[0]['id']}", bearer, library)
    write("character", character)

    root = get(f"/api/nodes?under={character['root']}&sort=name", bearer, library)
    write("character-root", root)
    seed = next(e["id"] for e in root["entries"] if e["name"] == "seed")
    write("seed-folder", get(f"/api/nodes?under={seed}&sort=name", bearer, library))

    write("projects", get("/api/projects", bearer, library))
    # The recursive media listing: `depth=all` with the media kinds asked for.
    write("reel", get("/api/nodes?depth=all&kind=image,video&sort=newest",
                      bearer, library))
    # The template library seeds with the library, so it belongs to this group
    # rather than the authoring one — no run has to have happened for it to
    # exist.
    write("templates", get("/api/templates", bearer, library))
    return character


def main() -> None:
    print(f"generating into {HERE}")
    video()
    if "--video" in sys.argv:
        return

    seed = "--runs" not in sys.argv
    runs = "--seed" not in sys.argv

    bearer = token()
    library = get("/api/libraries", bearer, None)[0]["id"]
    print(f"capturing from {API} into {HERE}")

    if seed:
        character = seed_group(bearer, library)
    else:
        # The authoring group still needs the character, and re-reading it is
        # cheaper than trusting the fixture on disk to be this stack's.
        characters = get("/api/characters", bearer, library)
        character = get(f"/api/characters/{characters[0]['id']}", bearer, library)

    if runs:
        authoring(bearer, library, character)


if __name__ == "__main__":
    main()

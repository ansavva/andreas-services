#!/usr/bin/env python3
"""Re-capture the e2e fixtures off the real API.

    studio/scripts/dev-up.sh                 # the API, on :8000
    python studio/frontend/e2e/fixtures/capture.py

**The fixtures are captured, not written.** A hand-written stub drifts from the
API silently and then asserts its own imagination; one taken from the thing it
stands in for cannot drift without somebody re-running this.

SCRUBBING IS NOT OPTIONAL AND IT IS WHY THIS IS A SCRIPT
--------------------------------------------------------
`/api/reel` answers with PRESIGNED S3 URLs, and a presigned URL carries the
signing key's ACCESS KEY ID in `X-Amz-Credential` along with a signature. Those
are not things to commit, and a `curl > fixture.json` puts them straight into
git — which is exactly what the first capture did. The signature expires in
fifteen minutes; the key id does not.

They also break the run. The browser fetches those URLs directly, so a "stubbed"
suite quietly reached real S3 for fourteen images — caught by the spec that
asserts nothing escapes to the network, which is the whole reason that spec is
there.

Every URL becomes `/e2e-asset.png`, which `support/api.ts` answers with a real
one-pixel PNG.

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
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
STUDIO = HERE.parents[2]
API = os.environ.get("STUDIO_E2E_API", "http://localhost:8000")

#: Anything that looks like a signed URL, wherever it appears.
SIGNED = re.compile(r"https?://[^\"\s]*X-Amz-(Signature|Credential)[^\"\s]*")
PLACEHOLDER = "/e2e-asset.png"


def scrub(value):
    """Every presigned URL replaced, at any depth."""
    if isinstance(value, str):
        return PLACEHOLDER if SIGNED.match(value) else value
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


def get(path: str, bearer: str, library: str | None):
    request = urllib.request.Request(f"{API}{path}")
    request.add_header("Authorization", f"Bearer {bearer}")
    if library:
        request.add_header("X-Studio-Library", library)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def write(name: str, body) -> None:
    cleaned = scrub(body)
    leaked = SIGNED.search(json.dumps(cleaned))
    assert not leaked, f"{name} still holds a signed URL: {leaked.group()[:80]}"
    (HERE / f"{name}.json").write_text(json.dumps(cleaned, indent=2) + "\n")
    print(f"  {name}.json")


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


def main() -> None:
    print(f"generating into {HERE}")
    video()
    if "--video" in sys.argv:
        return

    bearer = token()
    libraries = get("/api/libraries", bearer, None)
    library = libraries[0]["id"]
    print(f"capturing from {API} into {HERE}")
    write("libraries", libraries)

    characters = get("/api/characters", bearer, library)
    write("characters", characters)
    character = get(f"/api/characters/{characters[0]['id']}", bearer, library)
    write("character", character)

    root = get(f"/api/nodes?parent={character['root']}", bearer, library)
    write("character-root", root)
    seed = next(node["id"] for node in root if node["name"] == "seed")
    write("seed-folder", get(f"/api/nodes?parent={seed}", bearer, library))

    write("projects", get("/api/projects", bearer, library))
    write("reel", get("/api/reel?sort=newest", bearer, library))


if __name__ == "__main__":
    main()

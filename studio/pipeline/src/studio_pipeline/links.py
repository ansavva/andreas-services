"""Where to LOOK at a thing — the web app's address for a run, a scene, a project.

The CLI prints ids, and an id is not a place. A person who has just drafted a
run, or been told a scene assembled, was left to open the app and find it by
hand; this is the one place that knows how the app spells an address, so every
command that prints an id can print the link beside it.

The shapes are the SPA's own (`frontend/src/utils/location.ts`), restated here
because the pipeline never reads the frontend:

    run      <web_url>/p/<project-id>/r/<run-id>
    scene    <web_url>/s/<scene-id>
    project  <web_url>/p/<project-id>

**A run's link carries its project**, which is why every builder here takes a
run record rather than an id: the row names its project, and the URL is also a
breadcrumb.

`web_url` comes from the profile in force — `profiles.py` says how it is
derived when nothing stored one. When nothing can supply it, every builder
answers `""` and every printer prints nothing: a missing link is better than a
wrong one, and `studio profile show` says which case this is.

Human output prints a `ui:  <link>` line on stderr beside the id it already
printed; a JSON document gets a `"ui"` field. The two are `ui_line` and `with_ui`
below, so a command decides which it is emitting and nothing else.
"""

from __future__ import annotations

from studio_pipeline import profiles


def web_url() -> str:
    """The app for the profile in force, without a trailing slash, or ``""``."""
    return profiles.value(profiles.WEB_FIELD, required=False).rstrip("/")


def project(project_id: str) -> str:
    base = web_url()
    return f"{base}/p/{project_id}" if base and project_id else ""


def run(record: dict) -> str:
    """One run, inside the project that owns it. Empty if either id is missing."""
    base = web_url()
    project_id = record.get("project") or ""
    run_id = record.get("id") or ""
    return f"{base}/p/{project_id}/r/{run_id}" if base and project_id and run_id else ""


def scene(record: dict) -> str:
    base = web_url()
    scene_id = record.get("id") or ""
    return f"{base}/s/{scene_id}" if base and scene_id else ""


def ui_line(link: str, indent: str = "") -> str:
    """The human line for a link, or ``""`` so a caller can print it unconditionally."""
    return f"{indent}ui:  {link}" if link else ""


def with_ui(document: dict, link: str) -> dict:
    """A JSON document with its ``ui`` field, or unchanged when there is no link.

    Absent rather than null: a consumer testing ``"ui" in doc`` gets the same
    answer as one reading ``doc.get("ui")``, and a document from a stack with no
    web app looks like the document always did.
    """
    return {**document, "ui": link} if link else document

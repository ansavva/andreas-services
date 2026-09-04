---
name: studio
description: >-
  Repo rule. Entry point for every task in studio/ — the AI media generation pipeline
  and the app that browses its output. Route to one of studio's own skills before
  starting: a studio-media-* skill for anything that changes media or an S3 record
  (an image, a clip, a character, a project, a run, a scene, a movie), or
  studio-code-pipeline for studio's own code. Those skills live in
  studio/.claude/skills/ and are NOT registered at session start, so use this first
  whenever a task mentions studio, generating or editing images or video, characters,
  projects, runs, scenes or movies.
---

# Route before working in `studio/`

This skill hands you off. The routing table, the data model and the command
surface live in `studio/CLAUDE.md` and in studio's own skills.

## Load studio's skills before doing the work

Nineteen skills live in `studio/.claude/skills/`, in two families. Route by what
the task **changes**, not by what it mentions:

| Changing… | Load |
|---|---|
| media, or a catalog record — an image, a clip, a character, a project, a run, a scene, a movie | a **`studio-media-*`** skill (eighteen) |
| studio's own code — anything under `pipeline/`, `backend/`, `frontend/`, `infra/` | **`studio-code-pipeline`** |

The table naming each one is in `studio/CLAUDE.md`, under "Which skill".

## They are not registered at session start

Skills in `studio/.claude/skills/` are directory-scoped: they register once you
have **read a file under `studio/`**, not when the session begins. A `Skill` call
before that returns `Unknown skill` — a timing artifact, not a missing skill, and
not a reason to fall back to raw `aws s3` calls. The session-start hook running
`dev-setup.sh` does not register them. So: read `studio/CLAUDE.md` first — the
hard rules and the full routing table — then call the skill it points you at.

## Read the hard rules before spending anything

Stated in full at the top of `studio/CLAUDE.md`. In brief:

- **Never name a production character in the repo.** Characters are catalog
  rows; code, docs, commits and PR titles use the `<name>` placeholder. A dev
  subject listed in `DEV_SUBJECTS` is the one exception.
- **Nothing runs unless a person tells it to.** Show the full payload
  (`--dry-run`), ask, submit only when told. The submit command is the act;
  there is no separate approve step.
- **S3 is the only origin.** Assets reach a model as presigned URLs, never uploads.
- **Local commands run against this machine's dev stack**, selected by the `dev`
  profile. Production is `studio --profile prod …`, and nothing confirms it.

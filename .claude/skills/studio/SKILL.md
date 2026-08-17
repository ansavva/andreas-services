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

This skill exists to hand you off. It deliberately restates nothing — the routing
table, the S3 layout and the command surface live in `studio/CLAUDE.md` and in
studio's own skills, and a second copy here would be a second copy to keep true.

## Load studio's skills before doing the work

Sixteen skills live in `studio/.claude/skills/`, in two families. Route by what
the task **changes**, not by what it mentions:

| Changing… | Load |
|---|---|
| media, or an S3 record — an image, a clip, a character, a project, a run | a **`studio-media-*`** skill |
| studio's own code — anything under `pipeline/`, `backend/`, `frontend/`, `infra/` | **`studio-code-pipeline`** |

The full table naming each of the sixteen is in `studio/CLAUDE.md`, under
"Which skill".

## They are not registered at session start

Skills in `studio/.claude/skills/` are directory-scoped: they register once you
have **read a file under `studio/`**, not when the session begins. A `Skill` call
before that returns `Unknown skill` — a timing artifact, not a missing skill, and
not a reason to fall back to raw `aws s3` calls.

The session-start hook running `dev-setup.sh` does **not** register them; shell
access to the directory is not the trigger.

So the order is:

1. Read `studio/CLAUDE.md` — the hard rules and the full routing table.
2. Call the skill it points you at, by bare name.

Step 1 is the step that also makes step 2 work, so following the docs in order is
enough.

## Read the hard rules before spending anything

They are stated in full at the top of `studio/CLAUDE.md`. In brief, so you know
they exist before you act:

- **Never name a character anywhere in the repo.** Characters are data in S3;
  code, docs, commits and PR titles use the `<name>` placeholder.
- **Never submit a generation without approval of the full payload.** Every
  generation costs money.
- **S3 is the only origin.** Assets reach a model as presigned URLs, never uploads.
- **Local runs against prod.** There is no dev bucket. A delete run locally is a
  delete in production.

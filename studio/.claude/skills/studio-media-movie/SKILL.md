---
name: studio-media-movie
description: Cut a project's SCENES into one movie — the tier above a scene. Use when several finished scenes should become a single deliverable, when a piece has real breaks in it (a change of place, time or subject) rather than needing to read as one continuous take, or when the user asks to assemble, join, or export a whole piece. Owns the cut order, the movie-vs-longer-scene decision, and what a movie leaves behind in S3. To extend one continuous take past a model's duration ceiling use studio-media-scene instead.
---

# studio-media-movie

A **movie** is a project's scenes cut together into one piece. It is the top of
the hierarchy, and the only thing it contributes is **order**:

```
generation cut  ⊂  shot  ⊂  scene  ⊂  movie
```

- a **generation cut** is a cut inside one submission (Kling `multi_prompt`)
- a **shot** is one run's output, used as a scene component
- a **scene** is shots stitched into one continuous take (`studio-media-scene`)
- a **movie** is scenes cut together (this skill)

## Before anything: which project?

A movie belongs to a project, and `--project` is never inferred. If the project
is not already settled in this conversation, **ask**, offering the existing ones
and the option of a new one:

```bash
studio projects list
studio projects new <project> --character <name>
```

## A movie, or a longer scene?

This is the decision this skill exists to get right, and the stitcher will not
make it for you — it joins whatever it is given.

**Cut a movie** when the piece has genuine breaks: a change of place, of time,
or of subject. The joins are hard cuts, so put them where a hard cut belongs.

**Extend a scene** (`studio-media-scene`) when it must read as one continuous take —
same location, same wardrobe, same light, motion carrying across the join. A
hard cut in the middle of what should be one take reads as a mistake, and no
amount of re-stitching fixes it.

If the answer is "some of both", that is normal: build each continuous stretch
as a scene, then cut those scenes into a movie.

## Ordering scenes

- **Cut on motion settling, not mid-gesture.** A scene that ends with the
  subject still moving hands the next scene a jolt. `studio frames grid` on each
  scene's output is the cheapest way to see how it ends.
- **Keep the grade and the audio bed consistent across scenes**, or accept that
  the cut will announce itself. The stitcher normalises geometry, never colour.
- **Watch the aspect and frame rate.** Scenes built on different models can
  disagree; when they do the movie re-encodes to the *first* scene's geometry
  and says so in `stitch.method`. Put the scene whose framing should win first.
- **A one-scene movie is just that scene.** Cutting it copies the file for no
  gain; the tool says so.

## Building one

```bash
studio scenes list <project>          # what there is to cut

studio movies new <project> --name <name> \
  --scene <project>/<scene_id> \
  --scene <project>/<scene_id> \
  --scene <project>/latest

studio movies show <project>/latest
studio movies outputs <project>/latest --presign
```

`--scene` is repeatable and **order is the cut order**. It takes a **sceneref**:
`<project>/<scene_id>`, `<project>/latest`, or a unique fragment of the id. A
scene has exactly one output, so there is no `#N`.

No approval gate applies here: a movie bills nothing. It is a stitch over material
already in the library. (The gate covers what is sent to a model — see the repo
CLAUDE.md.)

## What it leaves behind

```
<project>/movies/<movie_id>/
    scenes/         each scene's output, copied in, numbered in cut order
    scenes/         each scene's output, copied in, numbered in cut order
    output/<name>.mp4
```

Same id shape as a run and a scene, so it sorts the same way.

**Derived, never a source of truth.** A movie names its scenes; the scenes name
their runs; the runs are the history. So a movie can always be rebuilt, and
nothing about it is worth protecting except the order.

**Scenes are copied in server-side** for the same reason a scene copies its
shots: the movie stays playable and re-cuttable while its scenes are rebuilt
around it, and the movie's record names the scene beside the copied node, so
copying does not lose lineage.

The record also carries `characters` — the union of the cast of every scene,
read back from the runs behind their shots. A movie can name who is in it
without a scan.

## Stitching

Handled by the shared ffmpeg layer, the same one the scene store uses, so a movie
and a scene join by identical rules:

- when every scene already agrees on codec, dimensions, frame rate and audio
  layout, the concat demuxer runs with `-c copy` — no re-encode, bit-for-bit
  the sources joined end to end;
- when they differ, scenes are normalised to the **first** scene's video
  geometry and a common audio layout, and `stitch.method` says so rather than
  it happening silently.

**The encode happens in the service, not on this machine.** `movies new`
resolves every sceneref, creates the movie row and asks the API to cut it; the
scenes are joined by a worker whose container image carries ffmpeg, and the
finished movie, the stitch report and the copies land on the record. The command
waits and prints as it goes — `Ctrl-C` abandons the wait, not the cut, and
`movies show` says how it went.

## Checking one

```bash
studio movies show <project>/latest        # durations, stitch method, cast
studio movies outputs <project>/latest --presign
```

`stitch.method` is the thing to read: a movie you expected to stream-copy that
re-encoded instead means the scenes disagreed about something, and the fix is
usually to rebuild the odd scene rather than to accept the re-encode.

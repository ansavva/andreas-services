import { useState } from "react";

import { Badge, Button, Text } from "@ansavva/design-system";

import type { RunAsset, Shot } from "../../types";
import { MotionEditor, MotionFields, draftOf, draftToShot, type Draft } from "./motionPrompt";
import { Frame, Sends } from "./Sends";
import { RunList } from "../run/RunList";

/**
 * The storyboard, split out of `ScenePage`.
 *
 * The page was 813 lines holding a board, a card, a prompt document, an editor
 * and a filmstrip — five things that change for different reasons. Nothing here
 * changed in the move.
 */

/**
 * One shot: what it is, the frames it is made of, and what it rendered into.
 *
 * The layout carries two axes on purpose — the cards run down the page in cut
 * order, and each card's filmstrip runs across it in the order the images reach
 * the model: the frame it opens on, then its panels, then the clip that came
 * out. A storyboard read as a list of prompts is what this page used to be, and
 * a list of prompts is the one thing a person cannot judge a shot from.
 */
export function ShotCard({
  shot,
  n,
  bracketed,
  onOpenRun,
  onView,
  onSave,
}: {
  shot: Shot;
  n: number;
  bracketed: boolean;
  onOpenRun: (run: string) => void;
  onView: (asset: RunAsset) => void;
  onSave: (shotId: string, body: Partial<Shot>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(shot));

  const motion = shot.motion;
  const caption = shot.beat || shot.prompt || shot.id;
  const duration = motion?.duration ?? shot.duration;

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      // The edited fields go back out as BOTH halves: `prompt_json` is the
      // document, `prompt` is that document serialized, and `prompt` is what the
      // model is actually given. Re-serialized from the parse rather than
      // hand-built, so every key the plan carried — including ones this form
      // does not show — survives the round trip in its original order.
      await onSave(shot.id, draftToShot(shot, draft));
      setEditing(false);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="body" tone="muted" className="tabular-nums">
          {String(n).padStart(2, "0")}
        </Text>
        <Text variant="body" className="min-w-48 flex-1 font-medium">
          {caption}
        </Text>
        {shot.status && (
          <Badge intent={shot.status === "rendered" ? "success" : "neutral"}>{shot.status}</Badge>
        )}
        {duration ? <Badge intent="neutral">{duration}s</Badge> : null}
        {motion?.model && <Badge intent="neutral">{motion.model}</Badge>}
        {/* One answer to "has this been shot", not two. `status` is computed
            from the plan and is what a storyboarded scene carries; the badge
            below is for a scene assembled from bare runs, which has no status
            at all. Showing both put `rendered` next to `not rendered` on the
            same card. */}
        {shot.run ? (
          <Button intent="ghost" size="sm" onClick={() => onOpenRun(shot.run as string)}>
            Open its run
          </Button>
        ) : (
          !shot.status && <Badge intent="warning">not rendered</Badge>
        )}
        {!editing && (
          <Button
            intent="ghost"
            size="sm"
            onClick={() => {
              setDraft(draftOf(shot));
              setSaveError(null);
              setEditing(true);
            }}
          >
            Edit
          </Button>
        )}
      </div>

      {/* The clip is OUTPUT and sits on its own; everything else a shot has is
          an INPUT, and `Sends` groups those by what they are sent as. The two
          used to be one filmstrip, which drew the same panel twice — once as a
          tile and once as the reference it becomes. */}
      {(shot.clip || (shot.takes ?? []).length > 0) && (
        <div className="flex flex-wrap gap-2">
          {shot.clip && (
            <Frame
              label="clip"
              asset={shot.clip}
              onOpen={onView}
              run={shot.run}
              onOpenRun={onOpenRun}
            />
          )}
          {/* **Earlier takes of this same shot, newest first.** A shot holds
              one `run`, so a retry used to erase the only pointer to what it
              replaced — the clip stayed in the project and nothing linked to
              it. Comparing a re-render against the take it replaced is the
              whole reason for re-rendering, and it was the one thing the board
              could not do. */}
          {(shot.takes ?? []).map((take) => (
            <Frame
              key={take.run ?? take.node ?? ""}
              label="earlier"
              hint="superseded"
              asset={take.clip}
              title="an earlier take of this shot"
              onOpen={onView}
              run={take.run}
              onOpenRun={onOpenRun}
            />
          ))}
        </div>
      )}

      {(shot.panels ?? []).length === 0 && !shot.clip && !shot.opens_on?.node && (
        <Text variant="caption" tone="muted">
          No panels — this shot renders from the previous shot&apos;s last frame.
        </Text>
      )}

      <Sends shot={shot} bracketed={bracketed} onView={onView} onOpenRun={onOpenRun} />

      {/* **The runs behind this shot, as a list rather than as links on tiles.**
          Every frame here came out of a run, and a link per tile answers "what
          made this picture" one picture at a time. Read together they answer a
          different question — what has been spent on this shot, what is still a
          draft, what failed — which is what a run list is for everywhere else in
          the app, drawn by the same component so a status colour means the same
          thing here as on a project or a character. */}
      {(shot.runs ?? []).length > 0 && (
        <section className="flex flex-col gap-1">
          <Text variant="caption" tone="muted">
            Runs
          </Text>
          <RunList runs={shot.runs ?? []} onOpen={(run) => onOpenRun(run.id)} />
        </section>
      )}

      {motion?.prompt &&
        (editing ? (
          <MotionEditor
            draft={draft}
            onChange={setDraft}
            onSave={save}
            onCancel={() => setEditing(false)}
            saving={saving}
            error={saveError}
          />
        ) : (
          <MotionFields motion={motion} />
        ))}
    </article>
  );
}

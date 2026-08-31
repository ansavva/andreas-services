import { useState } from "react";

import { Badge, Button, Tabs, Text } from "@ansavva/design-system";

import type { RunAsset, Shot } from "../../types";
import { Prompt } from "../run/RunPlan";
import { OutputPanel } from "../media/OutputPanel";
import {
  MotionEditor,
  draftOf,
  draftToShot,
  parsePrompt,
  type Draft,
} from "./motionPrompt";
import { Sends } from "./Sends";
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
  frameHref,
  onSave,
}: {
  shot: Shot;
  n: number;
  bracketed: boolean;
  onOpenRun: (run: string) => void;
  onView: (asset: RunAsset) => void;
  /** Where a frame opens, as an address — the scene owns the `?in=` context. */
  frameHref: (asset: RunAsset) => string;
  onSave: (shotId: string, body: Partial<Shot>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(shot));

  const [pane, setPane] = useState("plan");
  /** Outputs are plural: the current clip plus every superseded take. */
  const outputCount = (shot.clip ? 1 : 0) + (shot.takes ?? []).length;
  const hasOutput = outputCount > 0;
  const runCount = (shot.runs ?? []).length;

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
    // A storyboard is a sequence, and a sequence of ruled panels reads as one
    // board where a stack of filled cards reads as a pile. The rule is on the
    // BOTTOM: the section heading already draws one above the first shot, and
    // a `border-t` here would have put two hairlines twelve pixels apart.
    <article className="flex flex-col gap-3 rounded-none border-b border-line py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text
          variant="body"
          tone="muted"
          family="mono"
          className="tabular-nums"
        >
          {String(n).padStart(2, "0")}
        </Text>
        <Text variant="body" className="min-w-48 flex-1 font-medium">
          {caption}
        </Text>
        {shot.status && (
          <Badge
            intent={shot.status === "rendered" ? "success" : "neutral"}
            className="font-mono"
          >
            {shot.status}
          </Badge>
        )}
        {duration ? (
          <Badge intent="neutral" className="font-mono tabular-nums">
            {duration}s
          </Badge>
        ) : null}
        {motion?.model && (
          <Badge intent="neutral" className="font-mono">
            {motion.model}
          </Badge>
        )}
        {/* One answer to "has this been shot", not two. `status` is computed
            from the plan and is what a storyboarded scene carries; the badge
            below is for a scene assembled from bare runs, which has no status
            at all. Showing both put `rendered` next to `not rendered` on the
            same card. */}
        {shot.run ? (
          <Button
            intent="ghost"
            size="sm"
            onClick={() => onOpenRun(shot.run as string)}
          >
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

      {/* **A shot is a small run screen.** Its own inputs on the left, its
          own output on the right, and the outputs are plural on purpose — a
          re-render does not erase the take it replaced, and comparing the two
          is the whole reason to re-render.

          Output first in the DOM, so one column below `lg` leads with the
          clip and needs no `order` override. Same mechanism as `RunPage`. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:items-start">
        {hasOutput && (
          <div className="flex flex-col gap-3 lg:col-start-2 lg:row-start-1">
            {/* Titled and ruled, exactly as the run screen heads its own
                column. A muted caption made a shot's output look like a label
                on a thumbnail rather than the other half of the page. */}
            <Text variant="title" className="border-b border-line pb-2">
              {outputCount === 1 ? "Outputs" : `Outputs · ${outputCount}`}
            </Text>
            {/* **The run screen's output panel, not a thumbnail.** A shot's
                clip is the thing being judged, so it plays where it is, is
                sized to the media rather than cropped into a tile, and its
                caption is a real link — the same three properties the run
                screen's output has, because it is the same component. */}
            <div className="flex flex-col gap-3">
              {shot.clip && (
                <OutputPanel
                  asset={shot.clip}
                  sole={outputCount === 1}
                  to={frameHref(shot.clip)}
                />
              )}
              {/* **Earlier takes of this same shot, newest first.** A shot holds
                  one `run`, so a retry used to erase the only pointer to what it
                  replaced — the clip stayed in the project and nothing linked to
                  it. Comparing a re-render against the take it replaced is the
                  whole reason for re-rendering. */}
              {(shot.takes ?? []).map((take) =>
                take.clip ? (
                  <OutputPanel
                    key={take.run ?? take.node ?? ""}
                    asset={take.clip}
                    sole={false}
                    to={frameHref(take.clip)}
                    badge={<Badge intent="neutral">earlier</Badge>}
                  />
                ) : null,
              )}
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-col gap-3 lg:col-start-1 lg:row-start-1">
          {/* `Inputs` is the heading and the tabs sit under it — the shape the
              run screen settled on, so a shot reads as a small one rather than
              as a differently-built thing that happens to be nearby. */}
          <Text variant="title" className="border-b border-line pb-2">
            Inputs
          </Text>

          {/* The runs are a tab rather than a section below, because they
              answer a different question from the inputs — what has been spent
              on this shot, what is still a draft, what failed — and stacking
              them pushed the motion prompt off the bottom of every card. */}
          <Tabs.Root value={pane} defaultValue="plan" onValueChange={setPane}>
            <Tabs.List className="overflow-x-auto border-b border-line">
              <Tabs.Tab value="plan">Plan</Tabs.Tab>
              <Tabs.Tab value="runs">
                Runs{runCount ? ` · ${runCount}` : ""}
              </Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="plan">
              <div className="flex min-w-0 flex-col gap-3 pt-3">
                {(shot.panels ?? []).length === 0 &&
                  !shot.clip &&
                  !shot.opens_on?.node && (
                    <Text variant="caption" tone="muted">
                      No panels — this shot renders from the previous
                      shot&apos;s last frame.
                    </Text>
                  )}

                <Sends
                  shot={shot}
                  bracketed={bracketed}
                  onView={onView}
                  onOpenRun={onOpenRun}
                />

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
                    // The run screen's own renderer, not a second one. A
                    // shot's `motion.prompt` IS a compiled prompt document —
                    // the same artifact a run's plan carries — and drawing it
                    // as a Subject / Action / Style list here while the run
                    // drew the document made one thing look like two.
                    <Prompt
                      prompt={parsePrompt(motion.prompt) ?? motion.prompt}
                    />
                  ))}
              </div>
            </Tabs.Panel>

            <Tabs.Panel value="runs">
              <div className="flex min-w-0 flex-col gap-3 pt-3">
                {runCount === 0 ? (
                  <Text variant="body" tone="muted">
                    Nothing has been run for this shot yet.
                  </Text>
                ) : (
                  <>
                    {/* **The runs behind this shot, as a list rather than as links on tiles.**
                  Every frame here came out of a run, and a link per tile answers "what
                  made this picture" one picture at a time. Read together they answer a
                  different question — what has been spent on this shot, what is still a
                  draft, what failed — which is what a run list is for everywhere else in
                  the app, drawn by the same component so a status colour means the same
                  thing here as on a project or a character. */}
                    <section className="flex flex-col gap-1">
                      <Text variant="caption" tone="muted">
                        Runs
                      </Text>
                      <RunList
                        runs={shot.runs ?? []}
                        onOpen={(run) => onOpenRun(run.id)}
                      />
                    </section>
                  </>
                )}
              </div>
            </Tabs.Panel>
          </Tabs.Root>
        </div>
      </div>
    </article>
  );
}

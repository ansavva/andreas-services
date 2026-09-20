import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { formatBytes } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { MediaThumb } from "../media/MediaThumb";
import { pressInApp } from "../common/pressInApp";

/** What a checkpoint file's name says: which save point, which expert. */
const CHECKPOINT = /(?:_(\d{9}))?_(high|low)_noise\.safetensors$/;
/**
 * What a sample's name says: which save point, which prompt. The pod files
 * the trainer's samples as `<stem>_<step:09d>_sample_<i>.jpg`, the final
 * step's unnumbered like the final pair, so a sample sits in the same row as
 * the checkpoint it was drawn with off the name alone.
 */
const SAMPLE = /(?:_(\d{9}))?_sample_(\d+)\.(?:jpe?g|png|webp)$/;

type Expert = "high" | "low";

/** A checkpoint file name taken apart: the stem, the save point (`null` for the final pair), the expert. */
export function checkpointName(name: string): { stem: string; step: number | null; expert: Expert } | null {
  const match = CHECKPOINT.exec(name);
  if (!match) return null;
  return {
    stem: name.slice(0, match.index),
    step: match[1] ? Number(match[1]) : null,
    expert: match[2] as Expert,
  };
}

interface Checkpoint {
  /** The save point, or `null` for the final pair the trainer writes unnumbered. */
  step: number | null;
  files: Partial<Record<Expert, RunAsset>>;
  /** The stills drawn with this pair, in prompt order — see `SAMPLE`. */
  samples: RunAsset[];
}

/**
 * The checkpoints a training run leaves, in step order.
 *
 * The trainer writes a pair per save point — `<stem>_000000250_high_noise`
 * and `_low_noise` — and an unnumbered pair at the end. As a list of tiles the
 * run page was sixteen bands in the order the pod uploaded them, which is not
 * the order anyone reads them in; a person wants to see the eight save points
 * and reach for the pair at one of them. The final pair sits last and says so.
 *
 * While the run is out, every save point the plan promises is a row, and a
 * row whose pair has not landed says so — the plan's `steps` and `save_every`
 * are what the trainer was told, so the list is already the size it will be.
 *
 * Each row also carries the samples drawn at that save point — the same
 * prompts and seed every time, so reading down the list is watching the face
 * emerge, and the weights stay something a person reaches for once a row
 * looks right.
 */
export function checkpointsOf(row: RunFeedRow): Checkpoint[] {
  const byStep = new Map<number | null, Checkpoint>();
  const params = row.plan?.params ?? {};
  const steps = typeof params.steps === "number" ? params.steps : 0;
  const every = typeof params.save_every === "number" ? params.save_every : 0;
  const at = (step: number | null): Checkpoint => {
    const found = byStep.get(step);
    if (found) return found;
    const made = { step, files: {}, samples: [] };
    byStep.set(step, made);
    return made;
  };
  if (steps > 0 && every > 0) {
    for (let step = every; step < steps; step += every) at(step);
  }
  at(null);
  const indexed: { step: number | null; index: number; asset: RunAsset }[] = [];
  for (const asset of row.outputs) {
    const name = asset.name ?? "";
    const pair = CHECKPOINT.exec(name);
    if (pair) {
      at(pair[1] ? Number(pair[1]) : null).files[pair[2] as Expert] = asset;
      continue;
    }
    const sample = SAMPLE.exec(name);
    if (sample) indexed.push({ step: sample[1] ? Number(sample[1]) : null, index: Number(sample[2]), asset });
  }
  // In prompt order, whatever order the pod uploaded them in.
  indexed.sort((a, b) => a.index - b.index);
  for (const { step, asset } of indexed) at(step).samples.push(asset);
  const rows = [...byStep.values()];
  rows.sort((a, b) => (a.step ?? Infinity) - (b.step ?? Infinity));
  return rows;
}

/** Whether a row's outputs are a trainer's, whatever the run's kind says. */
export function hasCheckpoints(row: RunFeedRow): boolean {
  return row.kind === "training" || row.outputs.some((a) => CHECKPOINT.test(a.name ?? ""));
}

export function CheckpointList({ row, flying }: { row: RunFeedRow; flying: boolean }) {
  const navigate = useNavigate();
  const rows = checkpointsOf(row).filter((c) => flying || c.files.high || c.files.low || c.samples.length > 0);
  const landed = rows.filter((c) => c.files.high && c.files.low).length;
  const size = row.outputs.find((a) => a.size && CHECKPOINT.test(a.name ?? ""))?.size;
  const total = rows.length;

  return (
    <div className="col-span-full flex min-w-0 flex-col gap-1.5" data-checkpoint-list="">
      {/* Whose LoRA this is, first. The files carry the character's slug,
          but a listing is read faster than a filename. */}
      <Text variant="caption" tone="muted">
        {row.cast[0]?.name ? <span className="font-medium text-ink">{row.cast[0].name}</span> : null}
        {row.cast[0]?.name ? " · " : ""}
        {typeof row.plan?.params.trigger === "string" ? (
          <>
            <span className="font-mono">{row.plan.params.trigger}</span>
            {" · "}
          </>
        ) : null}
        {flying
          ? `${landed} of ${total} checkpoint pairs so far`
          : `${landed} checkpoint pair${landed === 1 ? "" : "s"}`}
        {size ? ` · ${formatBytes(size)} each` : ""}
      </Text>
      <ol className="divide-y divide-line border border-line bg-card">
        {rows.map((c) => {
          const pending = !c.files.high || !c.files.low;
          const where = c.step === null ? "" : ` at step ${c.step}`;
          return (
            <li
              key={c.step ?? "final"}
              className="flex flex-col gap-1.5 px-3 py-1.5"
              data-checkpoint={c.step ?? "final"}
            >
              <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3">
                <Text variant="body" weight={c.step === null ? "medium" : "regular"} className="whitespace-nowrap tabular-nums">
                  {c.step === null ? `final · ${row.plan?.params.steps ?? ""}`.trim() : `step ${c.step}`}
                </Text>
                {(["high", "low"] as const).map((expert) => {
                  const asset = c.files[expert];
                  if (!asset) {
                    return (
                      <Text key={expert} variant="caption" tone="muted" className="tabular-nums">
                        {pending && flying ? "…" : "—"}
                      </Text>
                    );
                  }
                  const to = objectPath(asset.node);
                  return (
                    <a
                      key={expert}
                      href={to}
                      onClick={pressInApp(navigate, to)}
                      aria-label={`Open ${expert}-noise checkpoint${where}`}
                      className="rounded-sm border border-line px-2 py-0.5 font-mono text-xs hover:bg-surface-alt focus-visible:outline focus-visible:outline-2"
                    >
                      {expert}
                    </a>
                  );
                })}
              </div>
              {c.samples.length > 0 && (
                /* The samples drawn with this pair, one per prompt, as a strip
                   that scrolls sideways on a phone rather than wrapping the
                   row into a wall — the list stays a list. Each opens the
                   picture's own page like any output. */
                <div className="-mx-3 flex gap-1 overflow-x-auto px-3 pb-0.5" data-samples="">
                  {c.samples.map((asset, index) => {
                    const to = objectPath(asset.node);
                    return (
                      <a
                        key={asset.node}
                        href={to}
                        onClick={pressInApp(navigate, to)}
                        aria-label={`Open sample ${index + 1}${where || " of the final checkpoint"}`}
                        // Big enough to read a face off, since that is the
                        // question; four across fit a phone's width.
                        className="block size-20 shrink-0 overflow-hidden rounded-sm border border-line focus-visible:outline focus-visible:outline-2 sm:size-24"
                      >
                        <MediaThumb
                          nodeId={asset.node}
                          url={asset.url}
                          name={asset.name}
                          isVideo={false}
                          poster={asset.poster}
                          aspect="square"
                        />
                      </a>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <Text variant="caption" tone="muted">
        A pair loads into <span className="font-mono">wan-2.2-i2v-lora</span> as
        <span className="font-mono"> --lora-high-key</span> / <span className="font-mono">--lora-low-key</span>.
      </Text>
    </div>
  );
}

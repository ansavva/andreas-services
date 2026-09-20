import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { formatBytes } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { MediaThumb } from "../media/MediaThumb";
import { pressInApp } from "../common/pressInApp";

/**
 * What a checkpoint file's name says: which save point, and which expert if
 * the trainer writes a pair. Wan 2.2 writes `<stem>_<step:09d>_high_noise`
 * and `_low_noise` (unnumbered at the end); a one-transformer trainer
 * (LTX-2.3, HunyuanVideo) writes `<stem>_<step:09d>` and a bare `<stem>`.
 * Both shapes come from the API's `expected_files`.
 */
const CHECKPOINT = /(?:_(\d{9}))?(?:_(high|low)_noise)?\.safetensors$/;
/**
 * What a sample's name says: which save point, which prompt. The pod files
 * the trainer's samples as `<stem>_<step:09d>_sample_<i>.jpg`, the final
 * step's unnumbered like the final pair, so a sample sits in the same row as
 * the checkpoint it was drawn with off the name alone.
 */
const SAMPLE = /(?:_(\d{9}))?_sample_(\d+)\.(?:jpe?g|png|webp)$/;

/** The slot a checkpoint file fills: one of Wan 2.2's two experts, or the one file of a one-stage model. */
type Expert = "high" | "low" | "file";

/**
 * Which inference entry a trainer's file loads into, by the trainer's model
 * id — what the footer under the list says. A trainer with no entry here
 * has no destination in studio yet, and the footer says that instead.
 */
const LOADS_INTO: Record<string, { model: string; flags: string }> = {
  "runpod-pod/ai-toolkit-wan22-14b": { model: "wan-2.2-i2v-lora", flags: "--lora-high-key / --lora-low-key" },
  "runpod-pod/ai-toolkit-ltx23-22b": { model: "ltx-2.3-i2v-lora", flags: "--lora-key" },
};

/** A checkpoint file name taken apart: the stem, the save point (`null` for the final one), the slot. */
export function checkpointName(name: string): { stem: string; step: number | null; expert: Expert } | null {
  const match = CHECKPOINT.exec(name);
  if (!match || match.index === 0) return null;
  return {
    stem: name.slice(0, match.index),
    step: match[1] ? Number(match[1]) : null,
    expert: (match[2] as "high" | "low" | undefined) ?? "file",
  };
}

interface Checkpoint {
  /** The save point, or `null` for the final checkpoint the trainer writes unnumbered. */
  step: number | null;
  files: Partial<Record<Expert, RunAsset>>;
  /** The stills drawn with this checkpoint, in prompt order — see `SAMPLE`. */
  samples: RunAsset[];
}

/**
 * The checkpoints a training run leaves, in step order.
 *
 * The trainer writes a checkpoint per save point — a pair for Wan 2.2, one
 * file for LTX-2.3 — and an unnumbered one at the end. As a list of tiles
 * the run page was sixteen bands in the order the pod uploaded them, which
 * is not the order anyone reads them in; a person wants to see the eight
 * save points and reach for the weights at one of them. The final one sits
 * last and says so.
 *
 * While the run is out, every save point the plan promises is a row, and a
 * row whose weights have not landed says so — the plan's `steps` and
 * `save_every` are what the trainer was told, so the list is already the
 * size it will be.
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
    const parsed = checkpointName(name);
    if (parsed) {
      at(parsed.step).files[parsed.expert] = asset;
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

/**
 * Whether this run's checkpoints are pairs. Read off what has landed when
 * anything has; before that, off the trainer — Wan 2.2 is the one that
 * splits its experts, and nothing else does.
 */
export function isPaired(row: RunFeedRow): boolean {
  for (const asset of row.outputs) {
    const parsed = checkpointName(asset.name ?? "");
    if (parsed) return parsed.expert !== "file";
  }
  return /wan22/.test(row.model ?? "");
}

/** Whether a row's outputs are a trainer's, whatever the run's kind says. */
export function hasCheckpoints(row: RunFeedRow): boolean {
  return row.kind === "training" || row.outputs.some((a) => checkpointName(a.name ?? "") !== null);
}

export function CheckpointList({ row, flying }: { row: RunFeedRow; flying: boolean }) {
  const navigate = useNavigate();
  const paired = isPaired(row);
  const slots: readonly Expert[] = paired ? ["high", "low"] : ["file"];
  const complete = (c: Checkpoint) => slots.every((slot) => c.files[slot]);
  const rows = checkpointsOf(row).filter((c) => flying || slots.some((slot) => c.files[slot]) || c.samples.length > 0);
  const landed = rows.filter(complete).length;
  const size = row.outputs.find((a) => a.size && checkpointName(a.name ?? ""))?.size;
  const total = rows.length;
  const unit = paired ? "checkpoint pair" : "checkpoint";
  const loads = LOADS_INTO[row.model ?? ""];

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
          ? `${landed} of ${total} ${unit}s so far`
          : `${landed} ${unit}${landed === 1 ? "" : "s"}`}
        {size ? ` · ${formatBytes(size)}${paired ? " each" : ""}` : ""}
      </Text>
      <ol className="divide-y divide-line border border-line bg-card">
        {rows.map((c) => {
          const pending = !complete(c);
          const where = c.step === null ? "" : ` at step ${c.step}`;
          return (
            <li
              key={c.step ?? "final"}
              className="flex flex-col gap-1.5 px-3 py-1.5"
              data-checkpoint={c.step ?? "final"}
            >
              <div className={`grid items-center gap-x-3 ${paired ? "grid-cols-[minmax(0,1fr)_auto_auto]" : "grid-cols-[minmax(0,1fr)_auto]"}`}>
                <Text variant="body" weight={c.step === null ? "medium" : "regular"} className="whitespace-nowrap tabular-nums">
                  {c.step === null ? `final · ${row.plan?.params.steps ?? ""}`.trim() : `step ${c.step}`}
                </Text>
                {slots.map((slot) => {
                  const asset = c.files[slot];
                  if (!asset) {
                    return (
                      <Text key={slot} variant="caption" tone="muted" className="tabular-nums">
                        {pending && flying ? "…" : "—"}
                      </Text>
                    );
                  }
                  const to = objectPath(asset.node);
                  return (
                    <a
                      key={slot}
                      href={to}
                      onClick={pressInApp(navigate, to)}
                      aria-label={slot === "file" ? `Open checkpoint${where}` : `Open ${slot}-noise checkpoint${where}`}
                      className="rounded-sm border border-line px-2 py-0.5 font-mono text-xs hover:bg-surface-alt focus-visible:outline focus-visible:outline-2"
                    >
                      {slot === "file" ? "lora" : slot}
                    </a>
                  );
                })}
              </div>
              {c.samples.length > 0 && (
                /* The samples drawn with this checkpoint, one per prompt, as a
                   strip that scrolls sideways on a phone rather than wrapping
                   the row into a wall — the list stays a list. Each opens the
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
        {loads ? (
          <>
            {paired ? "A pair loads into " : "A file loads into "}
            <span className="font-mono">{loads.model}</span> as <span className="font-mono">{loads.flags}</span>.
          </>
        ) : (
          "No hosted endpoint loads this trainer's LoRA yet."
        )}
      </Text>
    </div>
  );
}

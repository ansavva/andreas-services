import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { formatBytes } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { pressInApp } from "../common/pressInApp";

/** What a checkpoint file's name says: which save point, which expert. */
const CHECKPOINT = /(?:_(\d{9}))?_(high|low)_noise\.safetensors$/;

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
 */
export function checkpointsOf(row: RunFeedRow): Checkpoint[] {
  const byStep = new Map<number | null, Checkpoint>();
  const params = row.plan?.params ?? {};
  const steps = typeof params.steps === "number" ? params.steps : 0;
  const every = typeof params.save_every === "number" ? params.save_every : 0;
  if (steps > 0 && every > 0) {
    for (let step = every; step < steps; step += every) byStep.set(step, { step, files: {} });
  }
  byStep.set(null, { step: null, files: {} });
  for (const asset of row.outputs) {
    const match = CHECKPOINT.exec(asset.name ?? "");
    if (!match) continue;
    const step = match[1] ? Number(match[1]) : null;
    const entry = byStep.get(step) ?? { step, files: {} };
    entry.files[match[2] as Expert] = asset;
    byStep.set(step, entry);
  }
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
  const rows = checkpointsOf(row).filter((c) => flying || c.files.high || c.files.low);
  const landed = rows.filter((c) => c.files.high && c.files.low).length;
  const size = row.outputs.find((a) => a.size)?.size;
  const total = rows.length;

  return (
    <div className="col-span-full flex min-w-0 flex-col gap-1.5" data-checkpoint-list="">
      <Text variant="caption" tone="muted">
        {flying
          ? `${landed} of ${total} checkpoint pairs so far`
          : `${landed} checkpoint pair${landed === 1 ? "" : "s"}`}
        {size ? ` · ${formatBytes(size)} each` : ""}
      </Text>
      <ol className="divide-y divide-line border border-line bg-card">
        {rows.map((c) => {
          const pending = !c.files.high || !c.files.low;
          return (
            <li
              key={c.step ?? "final"}
              className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 px-3 py-1.5"
              data-checkpoint={c.step ?? "final"}
            >
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
                    aria-label={`Open ${expert}-noise checkpoint${c.step === null ? "" : ` at step ${c.step}`}`}
                    className="rounded-sm border border-line px-2 py-0.5 font-mono text-xs hover:bg-surface-alt focus-visible:outline focus-visible:outline-2"
                  >
                    {expert}
                  </a>
                );
              })}
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

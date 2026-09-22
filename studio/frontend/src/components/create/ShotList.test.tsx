import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { ModelEntry } from "../../types";
import { ShotList, ShotsPanel, parseShots, shotListOf, tallyOf } from "./ShotList";

afterEach(cleanup);

const TWO = JSON.stringify([
  { prompt: "stands in the rain", duration: 5 },
  { prompt: "he exhales", duration: 3 },
]);

/** Kling: a shots field and a cut ceiling, both off the registry entry. */
const KLING: ModelEntry = {
  key: "kling",
  model: "kwaivgi/kling-v3-omni-video",
  kind: "video",
  skill: "studio-media-kling",
  video: { shots: "multi_prompt", max_cuts: 6 },
  // The live schema read is refused in tests, so the snapshot is what says
  // how long the clip is — see `durationOf`.
  snapshot: { duration: { default: 5, minimum: 3, maximum: 15 } },
};

/** A model with no multi-shot mode at all. */
const SEEDANCE: ModelEntry = {
  key: "seedance",
  model: "bytedance/seedance-2.0",
  kind: "video",
  skill: "studio-media-seedance",
  video: { max_cuts: null },
};

function list(value: unknown, duration: number | null = 8, max: number | null = 6) {
  const onChange = vi.fn();
  render(
    <TestProviders>
      <ShotList value={value} duration={duration} max={max} onChange={onChange} />
    </TestProviders>,
  );
  return onChange;
}

function panel(entry: ModelEntry, params: Record<string, unknown> = {}) {
  const onParams = vi.fn();
  const view = render(
    <TestProviders>
      <ShotsPanel entry={entry} params={params} onParams={onParams} />
    </TestProviders>,
  );
  const seed = (next: Record<string, unknown>) =>
    view.rerender(
      <TestProviders>
        <ShotsPanel entry={entry} params={next} onParams={onParams} />
      </TestProviders>,
    );
  return { onParams, seed };
}

// --- the switch, and where the boxes live ---------------------------------

it("offers multi-shot only on a model that can be cut", () => {
  panel(SEEDANCE);
  expect(screen.queryByLabelText("Multi-shot")).toBeNull();
  cleanup();
  panel(KLING);
  expect(screen.getByLabelText("Multi-shot")).toBeTruthy();
});

it("is off until it is turned on, and shows no boxes while it is", () => {
  panel(KLING);
  expect(screen.queryByRole("textbox", { name: "Shot 1" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Add a shot" })).toBeNull();
});

it("turning it on opens two boxes that already split the clip", () => {
  const { onParams } = panel(KLING, { duration: 9 });
  fireEvent.click(screen.getByLabelText("Multi-shot"));
  expect(JSON.parse(onParams.mock.calls[0]?.[0].multi_prompt as string)).toEqual([
    { prompt: "", duration: 4 },
    { prompt: "", duration: 5 },
  ]);
});

it("turning it off unsets the field rather than sending an empty array", () => {
  const { onParams } = panel(KLING, { duration: 8, multi_prompt: TWO });
  fireEvent.click(screen.getByLabelText("Multi-shot"));
  expect(onParams).toHaveBeenLastCalledWith({ duration: 8 });
});

it("opens already on when the draft arrived with beats in it", () => {
  panel(KLING, { duration: 8, multi_prompt: TWO });
  expect((screen.getByRole("textbox", { name: "Shot 1" }) as HTMLTextAreaElement).value).toBe(
    "stands in the rain",
  );
  expect(screen.getByText("8s of 8s")).toBeTruthy();
});

it("measures the beats against the duration the run will actually go out with", () => {
  // Nothing set, so the model's own default is the length — an untouched
  // duration chip writes no param and the clip is still five seconds.
  panel(KLING, { multi_prompt: JSON.stringify([{ prompt: "one beat", duration: 3 }]) });
  expect(screen.getByText("3s of 5s — 2s short")).toBeTruthy();
});

// --- the boxes ------------------------------------------------------------

it("draws a box per beat, not the JSON it is stored as", () => {
  list(TWO);
  expect(
    (screen.getByRole("textbox", { name: "Shot 1" }) as HTMLTextAreaElement).value,
  ).toBe("stands in the rain");
  expect((screen.getByLabelText("Shot 2 seconds") as HTMLInputElement).value).toBe("3");
  expect(screen.queryByText(/\{"prompt"/)).toBeNull();
});

it("writes the field back as the JSON string the model takes", () => {
  const onChange = list(TWO);
  fireEvent.change(screen.getByRole("textbox", { name: "Shot 2" }), {
    target: { value: "he turns away" },
  });
  expect(JSON.parse(onChange.mock.calls[0]?.[0] as string)).toEqual([
    { prompt: "stands in the rain", duration: 5 },
    { prompt: "he turns away", duration: 3 },
  ]);
});

it("a new shot opens with the seconds that are left over", () => {
  const onChange = list(TWO, 12);
  fireEvent.click(screen.getByRole("button", { name: "Add a shot" }));
  expect(JSON.parse(onChange.mock.calls[0]?.[0] as string)[2]).toEqual({
    prompt: "",
    duration: 4,
  });
});

it("stops at the model's cut ceiling", () => {
  const six = JSON.stringify(
    Array.from({ length: 6 }, (_, at) => ({ prompt: `beat ${at}`, duration: 1 })),
  );
  list(six, 6);
  expect(screen.getByRole("button", { name: "Add a shot" }).hasAttribute("disabled")).toBe(
    true,
  );
});

it("removing a shot leaves the rest in order", () => {
  const onChange = list(TWO);
  fireEvent.click(screen.getByRole("button", { name: "Remove shot 1" }));
  expect(JSON.parse(onChange.mock.calls[0]?.[0] as string)).toEqual([
    { prompt: "he exhales", duration: 3 },
  ]);
});

it("moving a shot swaps it with its neighbour", () => {
  const onChange = list(TWO);
  fireEvent.click(screen.getByRole("button", { name: "Move shot 2 earlier" }));
  expect(
    JSON.parse(onChange.mock.calls[0]?.[0] as string).map((s: { prompt: string }) => s.prompt),
  ).toEqual(["he exhales", "stands in the rain"]);
});

it("hands something it cannot read back as text, unchanged", () => {
  list('[{"prompt": "half a th');
  const field = screen.getByRole("textbox", { name: "Shots" }) as HTMLTextAreaElement;
  expect(field.value).toBe('[{"prompt": "half a th');
  expect(screen.getByText(/not a list of shots/)).toBeTruthy();
});

// --- the arithmetic -------------------------------------------------------

it("parses nothing into no beats, and a non-list into nothing at all", () => {
  expect(parseShots(undefined)).toEqual([]);
  expect(parseShots("")).toEqual([]);
  expect(parseShots('{"prompt":"one"}')).toBeNull();
  expect(parseShots("[1, 2]")).toBeNull();
  expect(parseShots('[{"prompt":"a","duration":2}]')).toEqual([
    { prompt: "a", duration: 2 },
  ]);
});

it("recognises a shot list by its shape, for the read side", () => {
  expect(shotListOf(TWO)?.length).toBe(2);
  expect(shotListOf("a negative prompt, not a list")).toBeNull();
  expect(shotListOf(5)).toBeNull();
  expect(shotListOf("[]")).toBeNull();
});

it("tallies an unset duration without claiming the beats are wrong", () => {
  expect(tallyOf([{ prompt: "a", duration: 9 }], null).tone).toBe("text-muted");
  expect(tallyOf([], 8).text).toBe("");
});

it("follows the params it is handed after it mounted — Edit on a draft", () => {
  // The panel mounts with the create bar, empty; pressing Edit on a draft
  // seeds the plan into it afterwards. Held in state, the switch stayed off
  // and the draft's beats were invisible but still on the wire.
  const { seed } = panel(KLING, {});
  expect(screen.queryByRole("textbox", { name: "Shot 1" })).toBeNull();
  seed({ duration: 8, multi_prompt: TWO });
  expect((screen.getByRole("textbox", { name: "Shot 1" }) as HTMLTextAreaElement).value).toBe(
    "stands in the rain",
  );
});

it("turning it off and on again gives the beats back", () => {
  const { onParams, seed } = panel(KLING, { duration: 8, multi_prompt: TWO });
  fireEvent.click(screen.getByLabelText("Multi-shot"));
  seed(onParams.mock.calls[0]?.[0] as Record<string, unknown>);
  expect(screen.queryByRole("textbox", { name: "Shot 1" })).toBeNull();
  fireEvent.click(screen.getByLabelText("Multi-shot"));
  expect(JSON.parse(onParams.mock.calls[1]?.[0].multi_prompt as string)).toEqual(
    JSON.parse(TWO),
  );
});

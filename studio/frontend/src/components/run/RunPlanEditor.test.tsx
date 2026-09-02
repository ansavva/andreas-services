import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../apis/client";
import { RunPlanEditor, added } from "./RunPlanEditor";
import { TestProviders } from "../../test-providers";
import type { ModelEntry, RunPlan, RunRecord, RunSend } from "../../types";

/**
 * Editing a draft.
 *
 * What these hold up is the part a screenshot cannot: that **only the half that
 * moved is written**. Each `PATCH` is a full replace of its half, so a save that
 * sent both every time would rewrite the send rows of a run whose prompt was the
 * only thing touched — and every rewrite of either half clears the approval, so
 * the cost of the extra call is a yes withdrawn for nothing.
 */

const patchRunPlan = vi.fn();
const previewPrompt = vi.fn();
const patchRunSends = vi.fn();
const getModel = vi.fn();
const getModelSchema = vi.fn();
const getCharacterSelection = vi.fn();
const getProject = vi.fn();
const getFolder = vi.fn();

vi.mock("../../apis/studio", () => ({
  patchRunPlan: (...args: unknown[]) => patchRunPlan(...args),
  previewPlanPrompt: (...args: unknown[]) => previewPrompt(...args),
  patchRunSends: (...args: unknown[]) => patchRunSends(...args),
  // The picker's listing call. Named here because the mock replaces the whole
  // module, and an unmocked `getFolder` would be `undefined` the moment the dialog
  // opens rather than at import.
  getFolder: (...args: unknown[]) => getFolder(...args),
  getAsset: vi.fn(() =>
    Promise.resolve({ url: "https://example.test/re-signed" }),
  ),
  // Read for its `root`, which is where the picker opens, and for the characters
  // the selection helper offers.
  getProject: (...args: unknown[]) => getProject(...args),
  getCharacters: vi.fn(() => Promise.resolve([])),
  getModel: (...args: unknown[]) => getModel(...args),
  getModelSchema: (...args: unknown[]) => getModelSchema(...args),
  getCharacterSelection: (...args: unknown[]) => getCharacterSelection(...args),
  // The cast editor's two calls. The module mock replaces everything, so an
  // unnamed one is `undefined` at the first render rather than at import — and
  // a `useResource` handed `undefined` never settles, which hangs the suite
  // rather than failing it.
  getTemplates: vi.fn(() => Promise.resolve({ blocks: {}, templates: [] })),
  setRunCharacters: vi.fn(() => Promise.resolve({})),
  getRun: vi.fn(() => Promise.resolve({})),
}));

/** The registry entry for a model that takes references and a start frame. */
function entry(over: Partial<ModelEntry> = {}): ModelEntry {
  return {
    key: "a-model",
    model: "owner/a-model",
    kind: "image",
    skill: "studio-media-a-model",
    images: { refs: "image_input", start: "start_image", max_refs: 4 },
    ...over,
  } as ModelEntry;
}

afterEach(cleanup);

beforeEach(() => {
  patchRunPlan.mockReset();
  patchRunSends.mockReset();
  getModel.mockReset();
  getModelSchema.mockReset();
  getCharacterSelection.mockReset();
  getProject.mockReset();
  getFolder.mockReset();
  getFolder.mockResolvedValue({
    folders: [],
    files: [],
    breadcrumbs: [],
    depth: "1",
    tags: {},
    sort: "name",
  });
  // The registry and the schema are unreachable unless a case says otherwise —
  // which is the degraded path, and is what every case predating them runs
  // through unchanged.
  getModel.mockRejectedValue(new Error("no registry"));
  getModelSchema.mockRejectedValue(new Error("no schema"));
  getProject.mockResolvedValue({
    id: "proj-1",
    root: "node-project",
    characters: [
      { id: "char-1", slug: "placeholder", display_name: "Placeholder" },
    ],
  });
});

function send(over: Partial<RunSend> = {}): RunSend {
  return {
    order: 1,
    field: "image_input",
    role: "reference",
    node: "node-1",
    name: "front.webp",
    url: "https://example.test/front.webp",
    source: { kind: "object" },
    ...over,
  } as RunSend;
}

function draft(over: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run-1",
    project: "proj-1",
    status: "draft",
    kind: "image",
    model: "a-model",
    engine: "replicate",
    created: "2026-08-20T00:00:00Z",
    folder: "node-folder",
    outputs: [],
    scenes: [],
    bindings: {},
    sends: [send(), send({ order: 2, node: "node-2", name: "profile.webp" })],
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a porch at dawn",
      params: { aspect_ratio: "9:16" },
      note: null,
    },
    plan_digest: "sha256:abc",
    approval: null,
    stale: false,
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

/** The plan body of the first `PATCH /plan` — read after asserting it was called. */
function planSent(): RunPlan {
  const [, plan] = patchRunPlan.mock.calls[0] ?? [];
  return plan as RunPlan;
}

/** The sends body of the first `PATCH /sends`. */
function sendsSent(): { field: string; role: string | null; node: string }[] {
  const [, sends] = patchRunSends.mock.calls[0] ?? [];
  return sends as { field: string; role: string | null; node: string }[];
}

function editor(run = draft(), onSaved = vi.fn()) {
  render(
    <TestProviders>
      <RunPlanEditor run={run} onSaved={onSaved} onChanged={vi.fn()} onCancel={vi.fn()} />
    </TestProviders>,
  );
  return onSaved;
}

describe("editing a plan", () => {
  it("writes the plan and leaves the images alone", async () => {
    patchRunPlan.mockResolvedValue(draft());
    const onSaved = editor();

    fireEvent.change(screen.getByLabelText("Prompt"), {
      target: { value: "a porch at dusk" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().prompt).toBe("a porch at dusk");
    expect(patchRunSends).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalled();
  });

  it("writes the images and leaves the plan alone", async () => {
    patchRunSends.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByLabelText("Move image 2 earlier"));
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(patchRunPlan).not.toHaveBeenCalled();
    expect(sendsSent().map((each) => each.node)).toEqual(["node-2", "node-1"]);
  });

  it("writes nothing at all when nothing was touched", async () => {
    editor();

    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).not.toHaveBeenCalled());
    expect(patchRunSends).not.toHaveBeenCalled();
  });

  it("removes an image", async () => {
    patchRunSends.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByLabelText("Remove image 1"));
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(sendsSent()).toHaveLength(1);
    expect(sendsSent()[0]?.node).toBe("node-2");
  });

  it("stores a number as a number and everything else as text", async () => {
    /**
     * The one place this form guesses, so it is the one place worth pinning: a
     * model that takes `duration: 8` and is handed `"8"` is a payload the
     * provider rejects, and `png` must not become anything other than `png`.
     */
    patchRunPlan.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByText("Add a parameter"));
    fireEvent.change(screen.getByLabelText("Parameter 2 name"), {
      target: { value: "duration" },
    });
    fireEvent.change(screen.getByLabelText("Parameter 2 value"), {
      target: { value: "8" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().params).toEqual({ aspect_ratio: "9:16", duration: 8 });
  });

  it("keeps a reconstructed plan reconstructed", async () => {
    /**
     * `PATCH /plan` replaces the plan whole, so anything not carried through is
     * dropped. A backfilled plan quietly becoming an authored one would be a
     * record claiming somebody wrote words that were read off a request
     * document — and the run page says which it is.
     */
    patchRunPlan.mockResolvedValue(draft());
    editor(
      draft({
        plan: {
          version: 1,
          origin: "backfilled",
          prompt: "a porch",
          params: {},
        },
      }),
    );

    fireEvent.change(screen.getByLabelText("Prompt"), {
      target: { value: "a porch at noon" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().origin).toBe("backfilled");
  });

  it("edits a structured prompt as fields, so it cannot stop being JSON", async () => {
    // **This replaces "refuses to save a structured prompt that stopped being
    // JSON".** That test guarded a textarea of raw JSON that had to stay valid:
    // a misplaced comma lost the save, and reading your own prompt meant reading
    // escaping. The document is studio's own, with a schema `studio prompt`
    // validates, so it is edited field by field — the way a scene's shot has
    // always edited it — and the invalid state the old test guarded is now
    // unreachable rather than caught.
    editor(
      draft({
        plan: {
          version: 1,
          origin: "authored",
          prompt: { subject: "a man on a porch", action: "he turns" },
          params: {},
        },
      }),
    );

    // No single `Prompt` box any more; one input per field of the document.
    expect(screen.queryByLabelText("Prompt")).toBeNull();
    fireEvent.change(screen.getByLabelText("Subject"), {
      target: { value: "a man on a porch at dawn" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    const sent = planSent().prompt as Record<string, unknown>;
    expect(sent.subject).toBe("a man on a porch at dawn");
    // The key the form did not show survives, because the document is rebuilt
    // from the original rather than from the form alone.
    expect(sent.action).toBe("he turns");
  });

  it("edits a document STORED AS A STRING as fields, and saves a string back", async () => {
    // **The case that shipped broken.** `studio prompt --emit prompt` produces
    // the compiled document as a JSON *string*, and `--prompt-json` stores it
    // that way — so every properly authored plan holds a string. `structured`
    // asked `typeof !== "string"`, which is false for all of them, and the form
    // fell through to the prose textarea: a person opened Edit on a real plan
    // and got raw JSON, which is the one thing this form exists to prevent.
    editor(
      draft({
        plan: {
          version: 1,
          origin: "authored",
          prompt: JSON.stringify({
            subject: "a man on a porch",
            action: "he turns",
          }),
          params: {},
        },
      }),
    );

    expect(screen.queryByLabelText("Prompt")).toBeNull();
    fireEvent.change(screen.getByLabelText("Subject"), {
      target: { value: "a man on a porch at dawn" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    const sent = planSent().prompt;
    // Still a string, because that is how it arrived — rewording a plan must
    // not quietly change the shape of the record.
    expect(typeof sent).toBe("string");
    const parsed = JSON.parse(sent as string) as Record<string, unknown>;
    expect(parsed.subject).toBe("a man on a porch at dawn");
    expect(parsed.action).toBe("he turns");
  });

  it("says that saving withdraws the approval, before anything is typed", () => {
    editor();

    expect(screen.getByText("withdraws the approval")).toBeTruthy();
  });
});

describe("the params form the schema drives", () => {
  it("draws the model's own inputs, and keeps the rest as rows", async () => {
    getModel.mockResolvedValue(entry());
    getModelSchema.mockResolvedValue({
      model: "owner/a-model",
      props: {
        aspect_ratio: { type: "string", enum: ["1:1", "9:16"] },
        image_input: { type: "array", items: { type: "string", format: "uri" } },
      },
      schemas: {},
    });
    editor();

    // The described key leaves the freeform rows and becomes a select.
    await waitFor(() => expect(screen.getByLabelText("aspect_ratio")).toBeTruthy());
    expect(screen.queryByDisplayValue("aspect_ratio")).toBeNull();
    // The image field is a SEND. Hard rule #3: it never becomes a param box.
    expect(screen.queryByLabelText("image_input")).toBeNull();
  });

  it("degrades to the freeform rows when the schema cannot be read, and says so", async () => {
    // A provider that is down must not take the editor with it — and "this model
    // takes these inputs" and "nobody could ask" are different claims.
    editor();

    await waitFor(() =>
      expect(screen.getByText(/Could not read/)).toBeTruthy(),
    );
    expect(screen.getByDisplayValue("aspect_ratio")).toBeTruthy();
    expect(screen.getByDisplayValue("9:16")).toBeTruthy();
  });
});

describe("which model input a new image binds to", () => {
  it("offers the registry's image fields as completions", async () => {
    // The datalist used to hold only what the run already bound, on the reasoning
    // that this app had no registry. It reads the API's copy now — the one the
    // pipeline reads too — so a run with no images is no longer a blank box.
    getModel.mockResolvedValue(entry());
    editor(draft({ sends: [] }));

    await waitFor(() => expect(getModel).toHaveBeenCalled());
    const offered = Array.from(
      document.querySelectorAll("#run-send-fields option"),
    ).map((option) => option.getAttribute("value"));
    expect(offered).toContain("image_input");
    expect(offered).toContain("start_image");
  });

  it("starts a video run's first image on the start frame", async () => {
    // The frame-first workflow: an empty video run gaining an image is a still
    // being handed over to be animated, and `image_input` there submits nowhere.
    getModel.mockResolvedValue(entry({ kind: "video" }));
    getFolder.mockResolvedValue({
      depth: "1",
      tags: {},
      folders: [],
      files: [
        {
          id: "node-7",
          name: "frame.webp",
          kind: "image",
          url: "https://example.test/frame.webp",
        },
      ],
      breadcrumbs: [],
      sort: "name",
    });
    patchRunSends.mockResolvedValue(draft());
    editor(draft({ kind: "video", sends: [] }));

    await waitFor(() => expect(getModel).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Add an image"));
    fireEvent.click(await screen.findByLabelText("frame.webp"));
    fireEvent.click(screen.getByText("Add 1"));

    await waitFor(() =>
      expect(screen.getByDisplayValue("start_image")).toBeTruthy(),
    );
    fireEvent.click(screen.getByText("Save the plan"));
    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(sendsSent()[0]?.field).toBe("start_image");
  });
});

describe("adding a character's references", () => {
  const selection = [
    { slot: 1, node: "node-9", name: "front.webp", group: "face", description: null, url: null },
    { slot: 2, node: "node-10", name: "side.webp", group: "face", description: null, url: null },
  ];

  it("appends them on the registry's own refs field, as references", async () => {
    getModel.mockResolvedValue(entry());
    getCharacterSelection.mockResolvedValue({
      selection,
      cap: 4,
      source: "default",
    });
    patchRunSends.mockResolvedValue(draft());
    editor(draft({ sends: [] }));

    await waitFor(() => expect(getModel).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Add references"));

    await waitFor(() => expect(getCharacterSelection).toHaveBeenCalled());
    // The cap is measured against the reference rows already there, not guessed.
    expect(getCharacterSelection).toHaveBeenCalledWith("char-1", {
      group: undefined,
      tag: undefined,
      limit: 4,
    });

    fireEvent.click(screen.getByText("Save the plan"));
    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(sendsSent()).toEqual([
      { field: "image_input", role: "reference", node: "node-9" },
      { field: "image_input", role: "reference", node: "node-10" },
    ]);
  });

  it("shows an over-cap refusal and adds nothing", async () => {
    // **Never silently truncated.** The route sends back the index it would have
    // had to drop precisely so the app can show it; keeping the first few would
    // be a generation nobody could account for afterwards.
    getModel.mockResolvedValue(entry());
    getCharacterSelection.mockRejectedValue(
      new ApiError("11 references match; the cap is 4", 409, "over_cap", {
        error: "over_cap",
        index: [
          { node: "node-9", name: "front.webp" },
          { node: "node-10", name: "side.webp" },
        ],
      }),
    );
    editor(draft({ sends: [] }));

    await waitFor(() => expect(getModel).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Add references"));

    await waitFor(() =>
      expect(screen.getByText("11 references match; the cap is 4")).toBeTruthy(),
    );
    expect(screen.getByText(/front\.webp/)).toBeTruthy();

    fireEvent.click(screen.getByText("Save the plan"));
    await waitFor(() => expect(patchRunPlan).not.toHaveBeenCalled());
    expect(patchRunSends).not.toHaveBeenCalled();
  });
});

  it("previews EXACTLY what the plan will store, beside the fields", async () => {
    /**
     * A structured prompt is six fields plus a camera block that compile into
     * one document, so the thing being edited and the thing being sent look
     * nothing alike. The preview reads the same expression `save` writes — two
     * implementations of "what gets stored" disagree invisibly afterwards,
     * because a run records the outcome and not the reasoning.
     */
    editor(
      draft({
        plan: {
          version: 1,
          origin: "authored",
          prompt: { subject: "a man on a porch", action: "he turns" },
          params: {},
        },
      }),
    );

    const preview = await screen.findByLabelText("Plan prompt preview");
    expect(JSON.parse(preview.textContent!)).toEqual({
      subject: "a man on a porch",
      action: "he turns",
    });

    fireEvent.change(screen.getByLabelText("Subject"), {
      target: { value: "a man on a porch at dawn" },
    });
    await waitFor(() =>
      expect(
        screen.getByLabelText("Plan prompt preview").textContent,
      ).toContain("at dawn"),
    );

    // And what it showed is what was written.
    fireEvent.click(screen.getByText("Save the plan"));
    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().prompt).toEqual(
      JSON.parse(screen.getByLabelText("Plan prompt preview").textContent!),
    );
  });


  it("offers this run's cast to cite, and saves the template beside the prompt", async () => {
    /**
     * **A `{` typed into a run's prompt used to be a brace on its way to a
     * model.** The cast is numbered by the run's own binding — `{character.1}`
     * is the first character bound to THIS run — because a slug is an attribute
     * a rename swaps, and every record here names entity ids for that reason.
     *
     * Both halves are saved: `plan_digest` has to cover what reaches the model,
     * so the API expands at save; the template survives so the next edit opens
     * onto what was written rather than onto finished prose.
     */
    previewPrompt.mockResolvedValue({
      prompt: "He wears a charcoal tee.",
      spans: [{ name: "character.1.top", start: 9, end: 24 }],
      characters: 1,
    });
    editor(
      draft({
        characters: ["char-1"],
        plan: {
          version: 1,
          origin: "authored",
          prompt: "He wears a charcoal tee.",
          template: "He wears {character.1.top}.",
          params: {},
        },
      }),
    );

    // The template is what is EDITED; the preview shows what it becomes.
    const box = await screen.findByLabelText("Prompt");
    await waitFor(() => expect(box.textContent).toContain("{character.1.top}"));
    // Without the `{character.1.top}` label the preview draws around it — see
    // "marks WHERE each citation landed".
    await waitFor(() => {
      const clone = screen
        .getByLabelText("Plan prompt preview")
        .cloneNode(true) as HTMLElement;
      clone.querySelectorAll("[data-label]").forEach((l) => l.remove());
      expect(clone.textContent).toBe("He wears a charcoal tee.");
    });

    fireEvent.click(screen.getByText("Save the plan"));
    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().template).toBe("He wears {character.1.top}.");
  });

  it("keeps a plain textarea when the run binds no character", async () => {
    /** A menu with no options is worse than no menu. */
    editor(draft({}));
    expect(await screen.findByLabelText("Prompt")).toBeInstanceOf(HTMLTextAreaElement);
  });

  it("marks WHERE each citation landed in the expansion", async () => {
    /**
     * An expanded prompt is a wall of prose in which nothing says which words
     * came from which citation — the one question a reader of it has. The spans
     * come from the same walk that filled the text, not a search afterwards.
     */
    previewPrompt.mockResolvedValue({
      prompt: "He wears a charcoal tee.",
      spans: [{ name: "character.1.top", start: 9, end: 23 }],
      characters: 1,
    });
    editor(
      draft({
        characters: ["char-1"],
        plan: { version: 1, origin: "authored", params: {},
                prompt: "He wears a charcoal tee.",
                template: "He wears {character.1.top}." },
      }),
    );

    const marked = await waitFor(() => {
      const found = document.querySelector('[data-block="character.1.top"]');
      if (!found) throw new Error("nothing marked");
      return found as HTMLElement;
    });
    expect(marked.textContent).toBe("{character.1.top}a charcoal tee");
    // The text itself is untouched — the marks are around it, not in it.
    const box = screen.getByLabelText("Plan prompt preview");
    const clone = box.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[data-label]").forEach((l) => l.remove());
    expect(clone.textContent).toBe("He wears a charcoal tee.");
  });

  it("adds a reference to the REFERENCE input, not to the start frame beside it", async () => {
    /**
     * **The bug that sent one image where six were shown.** Both field and role
     * were copied off the previous row, so a run whose first row is the start
     * frame gave every image added after it `field: "image"` — and `image`
     * takes one value, so `bindings_of` kept the first and discarded the rest.
     * The page showed six images and the provider got one, with
     * `reference_images` absent entirely.
     */
    const row = added(
      { id: "node-b", name: "b.png", kind: "image" } as never,
      [{ key: "k", field: "image", role: "start", node: "node-a", name: "a.png" } as never],
      "image",
      { start: "image", refs: "reference_images" },
    );
    expect(row.field).toBe("reference_images");
    expect(row.role).toBe("reference");
  });

  it("still starts a video run's first image on the start frame", () => {
    /** The one case with nothing to reason from, which is what `first` is for. */
    const row = added(
      { id: "node-a", name: "a.png", kind: "image" } as never,
      [],
      "image",
      { start: "image", refs: "reference_images" },
    );
    expect(row.field).toBe("image");
  });

  it("does not copy a SCALAR field onto a second image", () => {
    const row = added(
      { id: "node-b", name: "b.png", kind: "image" } as never,
      [{ key: "k", field: "last_frame", role: "end", node: "node-a", name: "a.png" } as never],
      null,
      { end: "last_frame", refs: "reference_images" },
    );
    expect(row.field).toBe("reference_images");
  });

  it("says when a scalar input is overloaded, and repoints it in one press", async () => {
    /**
     * **The state real runs are already in.** `_check_scalar_fields` refuses it
     * at submit now, but the rows were written that way before that existed,
     * and a refusal at submit is later than a person can act on comfortably.
     */
    getModel.mockResolvedValue(entry({ kind: "video" }));
    editor(
      draft({
        sends: [
          { field: "start_image", role: "start", node: "node-a", name: "a.png",
            order: 0, source: null, url: null } as unknown as RunSend,
          { field: "start_image", role: "reference", node: "node-b", name: "b.png",
            order: 0, source: null, url: null } as unknown as RunSend,
          { field: "start_image", role: "reference", node: "node-c", name: "c.png",
            order: 0, source: null, url: null } as unknown as RunSend,
        ],
      }),
    );

    expect(
      await screen.findByText(/start_image takes one image, and 3 name it/i),
    ).toBeTruthy();
    fireEvent.click(screen.getByText(/Move the 2 reference\(s\) to image_input/));

    // The start frame keeps the scalar; the references move.
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Model input for image 1") as HTMLInputElement).value,
      ).toBe("start_image"),
    );
    for (const n of [2, 3]) {
      expect(
        (screen.getByLabelText(`Model input for image ${n}`) as HTMLInputElement).value,
      ).toBe("image_input");
    }
    await waitFor(() =>
      expect(screen.queryByText(/takes one image, and/i)).toBeNull(),
    );
  });

  it("drops a STALE template rather than letting it overwrite the edit", async () => {
    /**
     * **A run duplicated from a templated one carries the original's template.**
     * `planOf` spreads it through untouched and the API expands whatever
     * template it is handed — so on a run with no cast to expand against, the
     * stale template silently overwrote the prompt and every edit was discarded
     * on save. The template has to track what is in the box or not be sent.
     */
    editor(
      draft({
        characters: [],
        plan: {
          version: 1,
          origin: "authored",
          prompt: "The original sentence.",
          template: "The original sentence.",
          params: {},
        },
      }),
    );

    fireEvent.change(await screen.findByLabelText("Prompt"), {
      target: { value: "An edited sentence." },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().prompt).toBe("An edited sentence.");
    expect(planSent()).not.toHaveProperty("template");
  });

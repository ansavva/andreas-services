import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SchemaParams,
  describedKeys,
  describedProps,
  enumOf,
  isUriShaped,
} from "./SchemaParams";
import { TestProviders } from "../../test-providers";
import type { ModelSchema } from "../../types";

/**
 * The params form, driven by the model's live schema.
 *
 * Two things are worth pinning here and neither is visible in a screenshot:
 * **what the form refuses to draw** — the prompt, and anything uri-shaped, which
 * is a send and never a param (hard rule #3) — and **that an untouched prop
 * writes nothing**, because `params` is inside the fingerprint.
 */

const schema: ModelSchema = {
  model: "owner/a-model",
  props: {
    prompt: { type: "string", "x-order": 0 },
    // The enum hidden behind a `$ref`, which is how Replicate emits nearly all
    // of them — the case a form reading `spec.enum` alone gets wrong.
    aspect_ratio: {
      allOf: [{ $ref: "#/components/schemas/aspect_ratio" }],
      default: "1:1",
      "x-order": 3,
    },
    output_format: { type: "string", enum: ["png", "webp"], "x-order": 4 },
    num_outputs: {
      type: "integer",
      minimum: 1,
      maximum: 4,
      default: 1,
      "x-order": 2,
    },
    disable_safety: { type: "boolean", default: false, "x-order": 5 },
    negative_prompt: { type: "string", "x-order": 6 },
    image_input: {
      type: "array",
      items: { type: "string", format: "uri" },
      "x-order": 1,
    },
    start_image: { type: "string", format: "uri", "x-order": 7 },
    // No `type`, no enum — nothing this form can honestly draw.
    lora_weights: { title: "LoRA weights", "x-order": 8 },
  },
  schemas: {
    aspect_ratio: { type: "string", enum: ["1:1", "16:9", "9:16"] },
  },
};

const onSet = vi.fn();

afterEach(() => {
  cleanup();
  onSet.mockReset();
});

function form(over: Partial<ModelSchema> = {}, values = {}) {
  render(
    <TestProviders>
      <SchemaParams
        schema={{ ...schema, ...over }}
        skip={new Set(["image_input", "start_image"])}
        values={values}
        onSet={onSet}
      />
    </TestProviders>,
  );
}

describe("what the schema form draws", () => {
  it("gives an enum a select whose blank option is the model default", () => {
    form();

    const select = screen.getByLabelText("Output format");
    expect(select.textContent).toContain("Model default");

    fireEvent.click(select);
    expect(screen.getByText("png")).toBeTruthy();
    expect(screen.getByText("webp")).toBeTruthy();
  });

  it("resolves an enum hiding behind an allOf/$ref", () => {
    // The one that decides whether this form is worth having: `aspect_ratio` is
    // the field most often wrong and it never carries its own `enum`.
    form();

    const select = screen.getByLabelText("Aspect ratio");
    fireEvent.click(select);
    expect(screen.getByText("16:9")).toBeTruthy();
    expect(screen.getByText("9:16")).toBeTruthy();
  });

  it("gives a number its range", () => {
    form();

    const input = screen.getByLabelText("Num outputs") as HTMLInputElement;
    expect(input.type).toBe("number");
    expect(input.min).toBe("1");
    expect(input.max).toBe("4");
  });

  it("gives a boolean a switch, and a way back to the model default", () => {
    form({}, { disable_safety: "true" });

    const toggle = screen.getByRole("switch", { name: "Disable safety" });
    expect(toggle.getAttribute("aria-checked")).toBe("true");

    fireEvent.click(screen.getByText("Use the model default"));
    expect(onSet).toHaveBeenCalledWith("disable_safety", null);
  });

  it("shows an unset boolean as the model default rather than as off", () => {
    // Off and unset are different records — one says a person chose false.
    form();

    const toggle = screen.getByRole("switch", { name: "Disable safety" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(toggle.parentElement?.textContent).toContain("Model default");
    expect(screen.queryByText("Use the model default")).toBeNull();
  });

  it("gives a plain string an input", () => {
    form();

    expect(screen.getByLabelText("Negative prompt")).toBeTruthy();
  });

  it("skips the prompt and everything uri-shaped", () => {
    // Hard rule #3 where a person could break it by typing: an image is a node
    // this library holds and reaches the provider as a presigned URL, so a text
    // box for one would only ever collect the wrong kind of URL.
    form();

    expect(screen.queryByLabelText("Prompt")).toBeNull();
    expect(screen.queryByLabelText("Image input")).toBeNull();
    expect(screen.queryByLabelText("Start image")).toBeNull();
  });

  it("leaves a shape it cannot draw to the freeform rows", () => {
    form();

    expect(screen.queryByLabelText("Lora weights")).toBeNull();
    expect(describedKeys(schema, new Set()).has("lora_weights")).toBe(false);
  });

  it("writes nothing for a prop nobody touched", () => {
    form();

    expect(onSet).not.toHaveBeenCalled();
  });

  it("clears a prop back to unset rather than to empty", () => {
    form({}, { num_outputs: "3" });

    fireEvent.change(screen.getByLabelText("Num outputs"), {
      target: { value: "" },
    });
    expect(onSet).toHaveBeenCalledWith("num_outputs", null);
  });

  it("draws nothing at all when the schema could not be read", () => {
    // The degraded path: `props` empty means "could not ask", and the editor's
    // freeform rows are what a person edits instead.
    form({ props: {}, schemas: {} });

    expect(screen.queryByLabelText("Aspect ratio")).toBeNull();
    expect(describedKeys(null, new Set()).size).toBe(0);
  });
});

describe("the schema, read", () => {
  it("orders by x-order and drops what it cannot draw", () => {
    expect(
      describedProps(schema, new Set(["image_input", "start_image"])).map(
        (each) => each.name,
      ),
    ).toEqual([
      "num_outputs",
      "aspect_ratio",
      "output_format",
      "disable_safety",
      "negative_prompt",
    ]);
  });

  it("follows a $ref only as far as an enum", () => {
    expect(
      enumOf({ allOf: [{ $ref: "#/components/schemas/nothing" }] }, {}),
    ).toBeNull();
    expect(enumOf({ enum: ["a"] }, {})).toEqual(["a"]);
  });

  it("knows an image field by its uri shape, single or in a list", () => {
    expect(isUriShaped({ type: "string", format: "uri" })).toBe(true);
    expect(
      isUriShaped({ type: "array", items: { type: "string", format: "uri" } }),
    ).toBe(true);
    expect(isUriShaped({ type: "string" })).toBe(false);
    expect(
      isUriShaped({ type: "array", items: { type: "string" } }),
    ).toBe(false);
  });

  it("offers no box for a provider credential", () => {
    /**
     * Found on a real schema — `openai_api_key` on the GPT Image entries, drawn
     * as an ordinary optional string. A plan is a record: it is stored in the
     * catalog, hashed into the fingerprint and rendered back on the run
     * page, so a key typed into it would be a secret written to a row and shown
     * to everyone who can read the run. Studio's provider credential lives on
     * the API.
     */
    form({
      props: {
        ...schema.props,
        openai_api_key: { type: "string", title: "OpenAI API key" },
        auth_token: { type: "string" },
      },
    });

    expect(screen.queryByLabelText("openai_api_key")).toBeNull();
    expect(screen.queryByLabelText("auth_token")).toBeNull();
    // The ordinary props beside them are untouched.
    expect(screen.getByLabelText("Output format")).toBeTruthy();
  });
});

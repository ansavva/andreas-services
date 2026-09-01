import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { Marked, unfilledIn } from "./UnfilledMarks";

afterEach(cleanup);

const REAL = "Wearing a plain <one plain colour, optional> <garment>, unbranded.";

it("finds every marker the blank bible leaves behind", () => {
  expect(unfilledIn(REAL)).toEqual(["<one plain colour, optional>", "<garment>"]);
});

it("finds none in a prompt whose bible is filled in", () => {
  expect(unfilledIn("Wearing a plain navy T-shirt, unbranded.")).toEqual([]);
});

it("catches the EMPTY marker, which is the one most likely to be left", () => {
  /**
   * Ten fields in the blank template had `<>` as their hint — a placeholder
   * saying nothing about what belongs in it, which is exactly why they get
   * left. The regex wanted a letter and three characters, so those ten reached
   * a model with nothing anywhere saying so. The template has real hints now;
   * every character written before it does not.
   */
  expect(unfilledIn("Wearing a plain <> and <>.")).toEqual(["<>", "<>"]);
  expect(unfilledIn("Called <Name>, in <recurring setting>.")).toEqual([
    "<Name>",
    "<recurring setting>",
  ]);
});

it("leaves a comparison in prose alone", () => {
  // A leading space is what separates a marker from `a < b … >` in a sentence.
  expect(unfilledIn("shot at f< 2.8 and the light > ambient")).toEqual([]);
});

it("draws each one where it sits, without changing the text", () => {
  /**
   * These reach a model verbatim — the template writes them into the fields a
   * person is meant to replace, and `top_text` reads whatever is there. The
   * assembled prompt showed them in the same weight as the prose around them
   * and left it to be noticed.
   */
  const { container } = render(<Marked text={REAL} />);
  expect(container.textContent).toBe(REAL);
  expect(screen.getByText("<garment>").className).toContain("border-dashed");
  expect(container.querySelectorAll("[data-unfilled]").length).toBe(2);
});

it("leaves prose alone when nothing is unfilled", () => {
  const { container } = render(<Marked text="A studio portrait, front on." />);
  expect(container.textContent).toBe("A studio portrait, front on.");
  expect(container.querySelector("[data-unfilled]")).toBeNull();
});

it("is not confused by a second call — the regex is global", () => {
  /**
   * A global regex carries `lastIndex`, so a component rendered twice found
   * nothing the second time. The reset is deliberate, and this is what says so.
   */
  expect(unfilledIn(REAL).length).toBe(2);
  expect(unfilledIn(REAL).length).toBe(2);
  render(<Marked text={REAL} />);
  expect(document.querySelectorAll("[data-unfilled]").length).toBe(2);
});

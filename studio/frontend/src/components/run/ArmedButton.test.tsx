import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ArmedButton } from "./ArmedButton";

afterEach(cleanup);

function draw(onFire = vi.fn().mockResolvedValue(undefined)) {
  render(
    <ArmedButton
      idle="Rerun"
      armed="Press again — this spends"
      busy="Running…"
      tooltip="Runs the same payload as a new attempt."
      onFire={onFire}
    />,
  );
  return onFire;
}

/**
 * The confirmation is the button changing under your finger. It is not a
 * formality either — the arming expires, and moving focus away or pressing
 * Escape takes it back, which `ConfirmDeleteButton` establishes and this
 * borrows wholesale.
 */
it("arms on the first press and calls nothing", () => {
  const onFire = draw();

  expect(screen.queryByRole("button", { name: /this spends/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Rerun" }));

  expect(onFire).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /Press again/ })).toBeTruthy();
});

it("fires on the second press, once", async () => {
  const onFire = draw();

  fireEvent.click(screen.getByRole("button"));
  fireEvent.click(screen.getByRole("button"));

  await waitFor(() => expect(onFire).toHaveBeenCalledTimes(1));
});

it("says what it will do on hover, through the trigger's description", async () => {
  draw();

  const button = screen.getByRole("button", { name: "Rerun" });
  fireEvent.focus(button);

  expect(await screen.findByText(/same payload as a new attempt/)).toBeTruthy();
  expect(button.getAttribute("aria-describedby")).toBeTruthy();
});

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ItemActions } from "./ItemActions";
import { ARMED_MS } from "../../hooks/useArmed";
import { TestProviders } from "../../test-providers";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function show(onDelete = vi.fn(() => Promise.resolve())) {
  render(
    <ItemActions
      name="clip.mp4"
      copyValue="a/b/clip.mp4"
      onRename={vi.fn()}
      onMove={vi.fn()}
      onDelete={onDelete}
    />,
    // The copy item reports through the toast now, so the provider is required.
    { wrapper: TestProviders },
  );
  fireEvent.click(screen.getByRole("button", { name: "Actions for clip.mp4" }));
  return onDelete;
}

const remove = () => screen.getByRole("menuitem", { name: /Delete|Confirm/ });

describe("the delete item, which arms rather than fires", () => {
  it("restates what it will destroy on the first press and keeps the menu open", () => {
    const onDelete = show();

    fireEvent.click(remove());

    expect(remove().textContent).toBe("Confirm — delete clip.mp4");
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("deletes on the second press", async () => {
    const onDelete = show();

    fireEvent.click(remove());
    fireEvent.click(remove());

    await waitFor(() => expect(onDelete).toHaveBeenCalledOnce());
  });

  it("expires, which it did not use to — a menu item could sit armed indefinitely", () => {
    /**
     * The menu's own copy of the arm state had no timeout. Closing the menu
     * disarmed it, but a menu left open is exactly the case a timeout is for.
     */
    vi.useFakeTimers();
    const onDelete = show();

    fireEvent.click(remove());
    act(() => vi.advanceTimersByTime(ARMED_MS));

    expect(remove().textContent).toBe("Delete");
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("disarms on Escape before the menu closes on it", () => {
    show();

    fireEvent.click(remove());
    fireEvent.keyDown(remove(), { key: "Escape" });

    expect(remove().textContent).toBe("Delete");
  });
});

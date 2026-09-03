import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopyKeyButton } from "../components/common/CopyKeyButton";
import { TestProviders } from "../test-providers";

afterEach(cleanup);

/**
 * The toast wiring, exercised through the one control every surface copies
 * with. A copy leaves nothing on screen, so the toast is the confirmation —
 * and `useToast` throws outside its provider by design, which is why this
 * renders under `TestProviders` exactly as the app renders under `App`.
 */
describe("copying to the clipboard", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn(() => Promise.resolve()) },
      configurable: true,
    });
  });

  it("says so in a toast, in the notifications region", async () => {
    render(<CopyKeyButton value="<name>/reference/pool/1.jpg" />, { wrapper: TestProviders });

    fireEvent.click(screen.getByRole("button", { name: "Copy path" }));

    const region = await screen.findByRole("region", { name: "Notifications" });
    await waitFor(() => expect(region.textContent).toContain("Copied to the clipboard"));
  });

  it("reports the refusal the same way, as a danger", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn(() => Promise.reject(new Error("denied"))) },
      configurable: true,
    });
    render(<CopyKeyButton value="<name>/reference/pool/1.jpg" />, { wrapper: TestProviders });

    fireEvent.click(screen.getByRole("button", { name: "Copy path" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("Could not copy to the clipboard"),
    );
  });
});

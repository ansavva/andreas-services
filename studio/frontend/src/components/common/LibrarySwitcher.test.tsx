import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Library } from "../../types";

// The two seams the provider has: where the list comes from, and where the
// chosen id goes. Both are mocked so a case can assert on either without a
// server or a real request.
vi.mock("../../apis/studio", () => ({ getLibraries: vi.fn() }));
vi.mock("../../apis/client", () => ({ setLibrary: vi.fn() }));

import { setLibrary } from "../../apis/client";
import { getLibraries } from "../../apis/studio";
import { LibraryProvider, STORAGE_KEY } from "../../context/LibraryContext";
import { LibrarySwitcher } from "./LibrarySwitcher";
import { TestProviders } from "../../test-providers";

const libraries = vi.mocked(getLibraries);
const chose = vi.mocked(setLibrary);

const MINE: Library = { id: "lib-0001", name: "Studio", role: "owner" };
const THEIRS: Library = { id: "lib-0002", name: "Archive", role: "member" };

// Testing Library only registers its own cleanup with Vitest globals on, and
// they are off here — an unmounted tree would stay in the document and the next
// case would find two switchers.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

/** Reports the URL, so "switching leaves the node you were on" is assertable. */
function Address() {
  return <span data-testid="address">{useLocation().pathname}</span>;
}

function renderAt(path = "/f/node-1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LibraryProvider>
        <LibrarySwitcher />
        <Address />
      </LibraryProvider>
    </MemoryRouter>,
  { wrapper: TestProviders },
  );
}

/** The switcher, once the list has landed. `null` when there is nothing to choose. */
function switcher() {
  return screen.queryByRole("combobox", { name: "Library" });
}

describe("a caller with one library", () => {
  it("sees no switcher, and the header is set anyway", async () => {
    libraries.mockResolvedValue([MINE]);

    renderAt();

    await waitFor(() => {
      expect(chose).toHaveBeenCalledWith(MINE.id);
    });
    // A picker with one entry is a question with one answer. The request header
    // is not conditional on it — see `apis/client.test.ts`.
    expect(switcher()).toBeNull();
  });
});

describe("a caller with two libraries", () => {
  it("gets a switcher naming both", async () => {
    libraries.mockResolvedValue([THEIRS, MINE]);

    renderAt();

    await waitFor(() => {
      expect(switcher()).not.toBeNull();
    });
    fireEvent.click(switcher()!);
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Archive",
      "Studio",
    ]);
  });

  it("opens on the one it opened on last time", async () => {
    // The API sorts by name, so `Archive` is what a first-time caller would get.
    // A returning one gets what they chose.
    window.localStorage.setItem(STORAGE_KEY, MINE.id);
    libraries.mockResolvedValue([THEIRS, MINE]);

    renderAt();

    await waitFor(() => {
      expect(chose).toHaveBeenCalledWith(MINE.id);
    });
  });

  it("ignores a stored library the caller is no longer in", async () => {
    // A revoked membership. Sending it would be a 403 on every request rather
    // than an empty listing, so the stored id is checked against the list.
    window.localStorage.setItem(STORAGE_KEY, "lib-revoked");
    libraries.mockResolvedValue([THEIRS, MINE]);

    renderAt();

    await waitFor(() => {
      expect(chose).toHaveBeenCalledWith(THEIRS.id);
    });
  });

  it("switching sends the header, stores the choice and leaves the node behind", async () => {
    libraries.mockResolvedValue([THEIRS, MINE]);

    renderAt("/f/node-1");
    await waitFor(() => {
      expect(switcher()).not.toBeNull();
    });

    fireEvent.click(switcher()!);
    fireEvent.click(screen.getByRole("option", { name: "Studio" }));

    await waitFor(() => {
      expect(chose).toHaveBeenLastCalledWith(MINE.id);
    });
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(MINE.id);
    // The node id in the URL belongs to the library that was just left, so
    // staying on it is a 403 on the next fetch.
    expect(screen.getByTestId("address").textContent).toBe("/");
  });
});

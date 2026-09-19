import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Account } from "../../types";

vi.mock("../../apis/studio", () => ({
  getAccount: vi.fn(),
  setAccountName: vi.fn(),
  uploadAccountAvatar: vi.fn(),
  removeAccountAvatar: vi.fn(),
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ email: "person@example.com", logout: vi.fn(), refresh: vi.fn() }),
}));

import {
  getAccount,
  removeAccountAvatar,
  setAccountName,
  uploadAccountAvatar,
} from "../../apis/studio";
import { TestProviders } from "../../test-providers";
import { AccountMenu } from "./AccountMenu";

const account = vi.mocked(getAccount);
const rename = vi.mocked(setAccountName);
const upload = vi.mocked(uploadAccountAvatar);
const remove = vi.mocked(removeAccountAvatar);

const EMPTY: Account = { name: null, avatar_url: null, updated_at: null };
const NAMED: Account = { name: "Ada Lovelace", avatar_url: null, updated_at: "2026-09-19T00:00:00Z" };
const PICTURED: Account = { ...NAMED, avatar_url: "https://bucket/accounts/sub/a.jpg?sig" };

function open(collapsed = false) {
  return render(
    <TestProviders>
      <AccountMenu collapsed={collapsed} />
    </TestProviders>,
  );
}

function openDialog() {
  fireEvent.click(screen.getByRole("button", { name: /^Account/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Name and picture…" }));
  return screen.getByRole("dialog");
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  account.mockResolvedValue(EMPTY);
});

describe("the trigger", () => {
  it("draws the address and its initial until a name is given", async () => {
    open();
    const trigger = await screen.findByRole("button", { name: "Account — person@example.com" });
    expect(trigger.textContent).toContain("person@example.com");
    expect(trigger.textContent).toContain("P");
  });

  it("draws the name and its initials once there is one", async () => {
    account.mockResolvedValue(NAMED);
    open();
    const trigger = await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    expect(trigger.textContent).toContain("Ada Lovelace");
    expect(trigger.textContent).toContain("AL");
    expect(trigger.textContent).not.toContain("person@example.com");
  });

  it("draws the picture over the initials when there is one", async () => {
    account.mockResolvedValue(PICTURED);
    open();
    const trigger = await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    const img = trigger.querySelector("img");
    expect(img?.getAttribute("src")).toBe(PICTURED.avatar_url);
  });

  it("collapsed, is the picture alone and still named", async () => {
    account.mockResolvedValue(NAMED);
    open(true);
    const trigger = await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    expect(trigger.textContent).toBe("AL");
  });
});

describe("the menu", () => {
  it("reads the name and the address, and offers the dialog", async () => {
    account.mockResolvedValue(NAMED);
    open();
    await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    fireEvent.click(screen.getByRole("button", { name: /^Account/ }));
    const heading = screen.getByRole("menuitem", { name: /Ada Lovelace/ });
    expect(heading.getAttribute("aria-disabled")).toBe("true");
    expect(heading.textContent).toContain("person@example.com");
    expect(screen.getByRole("menuitem", { name: "Name and picture…" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeTruthy();
  });
});

describe("the dialog", () => {
  it("saves a typed name and the trigger follows", async () => {
    rename.mockResolvedValue(NAMED);
    open();
    await screen.findByRole("button", { name: "Account — person@example.com" });
    openDialog();
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: " Ada Lovelace " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(rename).toHaveBeenCalledTimes(1));
    expect(rename.mock.calls[0]![0]).toBe("Ada Lovelace");
    await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("uploads a picked picture as a data URL, and offers Remove once there is one", async () => {
    upload.mockResolvedValue(PICTURED);
    remove.mockResolvedValue(NAMED);
    account.mockResolvedValue(NAMED);
    open();
    await screen.findByRole("button", { name: "Account — Ada Lovelace" });
    openDialog();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();

    const file = new File([new Uint8Array([137, 80, 78, 71])], "me.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Choose a picture"), { target: { files: [file] } });
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    expect(upload.mock.calls[0]![0]).toMatch(/^data:image\/png;base64,/);

    const removeButton = await screen.findByRole("button", { name: "Remove" });
    fireEvent.click(removeButton);
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove" })).toBeNull());
    // Back to initials, not to a blank circle: the trigger's letters are drawn again.
    const trigger = screen.getByRole("button", { name: "Account — Ada Lovelace" });
    expect(trigger.querySelector("img")).toBeNull();
    expect(trigger.textContent).toContain("AL");
  });

  it("refuses the wrong kind of file before anything is sent", async () => {
    open();
    await screen.findByRole("button", { name: "Account — person@example.com" });
    openDialog();
    const file = new File(["GIF89a"], "me.gif", { type: "image/gif" });
    fireEvent.change(screen.getByLabelText("Choose a picture"), { target: { files: [file] } });
    await screen.findByText("Choose a PNG, JPEG or WebP image.");
    expect(upload).not.toHaveBeenCalled();
  });

  it("shows why a save failed and stays open", async () => {
    rename.mockRejectedValue(new Error("name must be 100 characters or fewer"));
    open();
    await screen.findByRole("button", { name: "Account — person@example.com" });
    openDialog();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("name must be 100 characters or fewer");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});

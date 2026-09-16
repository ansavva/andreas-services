import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The three states of the sign-up screen, with both Cognito calls stubbed.
 *
 * The button gating is what is worth pinning: an invite code is required
 * before "Create account" enables, because a sign-up without one is refused
 * by the pool and the refusal reads like a broken form.
 */

const signUp = vi.fn();
const confirmSignUp = vi.fn();
const resendCode = vi.fn();
const login = vi.fn();
vi.mock("../auth/signup", () => ({
  signUp: (...args: unknown[]) => signUp(...args),
  confirmSignUp: (...args: unknown[]) => confirmSignUp(...args),
  resendCode: (...args: unknown[]) => resendCode(...args),
}));
vi.mock("../auth/oauth", () => ({ login: (...args: unknown[]) => login(...args) }));

import { SignUpPage } from "./SignUpPage";
import { TestProviders } from "../test-providers";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function type(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("SignUpPage", () => {
  it("needs an address, a long-enough password and an invite code before it will register", () => {
    render(<SignUpPage />, { wrapper: TestProviders });
    const button = screen.getByRole("button", { name: "Create account" });

    expect(button).toHaveProperty("disabled", true);
    type(/^Email$/, "new@example.com");
    type(/^Password$/, "Correct-horse-1");
    expect(button).toHaveProperty("disabled", true);
    type(/Invite code/, "open-sesame");
    expect(button).toHaveProperty("disabled", false);
  });

  it("registers with the code, confirms, then offers sign-in", async () => {
    signUp.mockResolvedValue("n***@e***.com");
    confirmSignUp.mockResolvedValue(undefined);
    render(<SignUpPage />, { wrapper: TestProviders });

    type(/^Email$/, "new@example.com");
    type(/^Password$/, "Correct-horse-1");
    type(/Invite code/, "open-sesame");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(screen.getByText("n***@e***.com")).toBeDefined());
    expect(signUp).toHaveBeenCalledWith("new@example.com", "Correct-horse-1", "open-sesame");

    type(/Confirmation code/, "424242");
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeDefined());
    expect(confirmSignUp).toHaveBeenCalledWith("new@example.com", "424242");

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledWith("/");
  });

  it("shows the pool's refusal and stays on the form", async () => {
    signUp.mockRejectedValue(new Error("Studio is invite-only."));
    render(<SignUpPage />, { wrapper: TestProviders });

    type(/^Email$/, "new@example.com");
    type(/^Password$/, "Correct-horse-1");
    type(/Invite code/, "wrong");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(screen.getByText("Studio is invite-only.")).toBeDefined());
    expect(screen.getByRole("button", { name: "Create account" })).toBeDefined();
  });
});

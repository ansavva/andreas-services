/**
 * Getting in: the sign-up page, and the first-library screen behind sign-in.
 *
 * Both are screens that the unit suites hold up piece by piece — the two
 * Cognito calls, the `POST`, the form's gating — and what neither can hold up
 * is the hand-off: that a confirmed sign-up lands on "Sign in", and that an
 * account in no library is offered a library rather than a dead end, and is
 * inside it the moment the create answers. Playwright's `page.route` is what
 * lets both run with no pool and no API: the Cognito endpoint is stubbed here
 * like `/api/**` is in `support/api.ts`.
 */
import { expect, test } from "@playwright/test";

import { LIBRARY, stubApi } from "./support/api";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

test.describe("sign-up", () => {
  test.skip(LIVE, "drives a stubbed pool; the live pool would email a real code");

  test("registers with the invite code, confirms, then offers sign-in", async ({ page }) => {
    const targets: string[] = [];
    await page.route("https://cognito-idp.us-east-1.amazonaws.com/", async (route) => {
      const target = route.request().headers()["x-amz-target"] ?? "";
      targets.push(target);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      if (target.endsWith(".SignUp")) {
        const metadata = body.ClientMetadata as Record<string, string>;
        if (metadata?.invite_code !== "open-sesame") {
          return route.fulfill({
            status: 400,
            contentType: "application/x-amz-json-1.1",
            body: JSON.stringify({
              __type: "UserLambdaValidationException",
              message: "PreSignUp failed with error That code is not an invite.",
            }),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/x-amz-json-1.1",
          body: JSON.stringify({ CodeDeliveryDetails: { Destination: "n***@e***.com" } }),
        });
      }
      return route.fulfill({ status: 200, contentType: "application/x-amz-json-1.1", body: "{}" });
    });

    await page.goto("/signup");
    await page.getByLabel("Email").fill("new@example.com");
    await page.getByLabel("Password").fill("Correct-horse-1");
    await page.getByLabel("Invite code").fill("wrong");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText("That code is not an invite.")).toBeVisible();

    await page.getByLabel("Invite code").fill("open-sesame");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText("n***@e***.com")).toBeVisible();

    await page.getByLabel("Confirmation code").fill("424242");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

    expect(targets.map((t) => t.split(".").pop())).toEqual(["SignUp", "SignUp", "ConfirmSignUp"]);
  });
});

test.describe("an account in no library", () => {
  test.skip(LIVE, "the live account is in a library");

  test("is offered a library, and is inside it once made", async ({ page }) => {
    await stubApi(page);
    await signIn(page, LIBRARY);
    // Over the stub, so the listing says "none" until the create has answered —
    // which is the state the screen is for, and the one no fixture captures.
    let created = false;
    await page.route("**/api/libraries", async (route) => {
      if (route.request().method() === "POST") {
        created = true;
        const body = route.request().postDataJSON() as { name: string };
        return route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({ id: LIBRARY, name: body.name, role: "owner", root: "node-root" }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: created ? JSON.stringify([{ id: LIBRARY, name: "Mine", role: "owner" }]) : "[]",
      });
    });

    await page.goto("/");
    await expect(page.getByText("Name your library")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create library" })).toBeDisabled();

    await page.getByLabel("Library name").fill("Mine");
    await page.getByRole("button", { name: "Create library" }).click();

    // No reload and no second listing: the context takes the created library
    // and the gate opens onto the routes.
    await expect(page.getByText("Name your library")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Create library" })).toHaveCount(0);
    expect(created).toBe(true);
  });
});

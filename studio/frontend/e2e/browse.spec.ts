/**
 * The screens, rendered.
 *
 * These cover the one thing the vitest suite deliberately does not: that file
 * argues its bar is *addressing*, and that the rest is "covered by typecheck and
 * the build". Typecheck cannot tell you a listing rendered, and a build cannot
 * tell you 54 images resolved.
 *
 * Every `/api/**` is fulfilled from fixtures captured off the real API against
 * the published dev-seed character — see `support/api.ts`.
 */
import { expect, test } from "@playwright/test";

import { CHARACTER, LIBRARY, fixture, stubApi } from "./support/api";
import { signIn } from "./support/session";

const SEED = fixture<Array<{ name: string; content_type: string }>>("seed-folder");

const LIVE = process.env.E2E_LIVE === "1";

test.beforeEach(async ({ page }) => {
  // In LIVE mode the real API answers and the developer's own browser session
  // is used — stubbing either would defeat the point of running live at all.
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

/**
 * Skip ONE spec in live mode, not the file.
 *
 * A module-level `test.skip(LIVE, …)` skips everything in the file, which is
 * how a whole suite reports as green having run nothing — the same shape as the
 * collection hook that once skipped all 373 backend tests and exited 0. This is
 * per-spec on purpose.
 */
function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

test("a seeded session reaches the app rather than the login form", async ({ page }) => {
  // `App.tsx` renders `<LoginForm />` unless `authenticated`, so if the seeded
  // token store stopped satisfying Amplify every spec below would fail with a
  // confusing selector error instead of this one sentence.
  //
  // Asserting on something only the SIGNED-IN shell has. An earlier version
  // asserted "no sign-in button", which also passed against the "Auth is not
  // configured" screen — a test that proved nothing.
  await page.goto("/");
  await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible();
});

test("the home page lists the seeded character with its real counts", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Characters (1)")).toBeVisible();
  // **`counts.files` was read by the CLI and sent by no route until this
  // branch**, so every character in every listing showed `0 files`. The fixture
  // is the API's own answer and carries 54.
  await expect(page.getByText(/0 references · 54 files/)).toBeVisible();
});

test("no request escapes to the network", async ({ page }) => {
  stubOnly("live traffic reaches :8000 and S3 by design");
  // What makes this suite safe to run anywhere: no AWS, no credentials, no
  // stack, and no Cognito. Registered BEFORE navigating — an earlier version
  // attached the listener afterwards and could not have seen anything.
  const escaped: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith("http://localhost:4173") && !url.startsWith("data:")) {
      escaped.push(url);
    }
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  expect(escaped).toEqual([]);
});

test("nothing 5xxs, so no fixture is missing", async ({ page }) => {
  stubOnly("there are no fixtures in live mode");
  // `stubApi` answers an unknown path with a 501 naming it, so a fixture that
  // was never captured is a failure here rather than a quietly empty screen.
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  expect(failures).toEqual([]);
});

test("the character page opens its seed pool", async ({ page }) => {
  await page.goto(`/c/${CHARACTER}`);
  await expect(page.getByText("jason").first()).toBeVisible();
});

test("the captured listing still says 49 jpeg and 5 png", async ({ page }) => {
  // **The reason the seed images were normalised at all.** Five of the 54
  // arrived as PNG bytes behind a `.jpg` name, and content type is derived from
  // the name — so all 54 would have been stored and served as JPEG. This
  // fixture is the API's own listing, so if that ever regresses the fixture is
  // re-captured and this fails.
  expect(SEED).toHaveLength(54);
  expect(SEED.filter((n) => n.content_type === "image/png")).toHaveLength(5);
  expect(SEED.filter((n) => n.content_type === "image/jpeg")).toHaveLength(49);
  expect(SEED.filter((n) => n.name.endsWith(".png"))).toHaveLength(5);
});

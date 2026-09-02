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

const SEED = fixture<{
  entries: Array<{ name: string; content_type: string }>;
}>("seed-folder").entries;

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

test("a seeded session reaches the app rather than the hosted sign-in page", async ({
  page,
}) => {
  // `App.tsx` redirects to Cognito Managed Login unless `authenticated`, so if
  // the seeded token store stopped satisfying `auth/oauth.ts` every spec below
  // would fail against a page that is not even served from this origin —
  // a confusing selector error instead of this one sentence.
  //
  // Asserting on something only the SIGNED-IN shell has. An earlier version
  // asserted "no sign-in button", which also passed against the "Auth is not
  // configured" screen — a test that proved nothing.
  //
  // Sign-out is inside the account menu now, so this opens it rather than
  // looking for a bare button. Both halves are kept deliberately: the account
  // trigger proves the signed-in shell rendered, and sign-out behind it proves
  // the menu is the real one and not an empty shell with the right label.
  await page.goto("/");
  const account = page.getByRole("button", { name: /account/i });
  await expect(account).toBeVisible();
  await account.click();
  await expect(page.getByRole("menuitem", { name: /sign out/i })).toBeVisible();
});

test("the header offers the three sections", async ({ page }) => {
  // The navigation this rework added. It is asserted here rather than trusted
  // to the screenshots because it is the one thing on every screen: if these
  // stop rendering, every page loses its way out at once.
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: /sections/i }).first();
  for (const label of ["Characters", "Projects", "Files"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
});

test("the home page lists the seeded character with its real counts", async ({
  page,
}) => {
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
    if (response.status() >= 500)
      failures.push(`${response.status()} ${response.url()}`);
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

/**
 * **Back is not the breadcrumb**, and `PageBar` now carries both.
 *
 * A crumb goes UP — to the folder or the project. Back goes where you actually
 * came from, and `?in=` makes those routinely different: a file opened from a
 * feed has an "up" it has never visited. The arrow only appears when there is
 * an entry to undo, because a cold share link's back leaves the app entirely.
 *
 * `exact: true` is not decoration: Playwright matches an accessible name as a
 * case-insensitive SUBSTRING, and a character's body-angle stills are named
 * "…back…", so a loose locator matches four tiles in the Recent grid and the
 * test fails on a page that is behaving perfectly.
 *
 * **These must navigate in-app, never with a second `page.goto`.** A `goto` is
 * a full document load, so React Router's `location.key` resets to `"default"`
 * and the arrow correctly hides — a test written that way fails against a
 * perfectly good implementation, which is exactly what happened while writing
 * this one.
 */
test("a back arrow appears once there is somewhere to go back to", async ({
  page,
}) => {
  stubOnly(
    "the arrow is router state, and the stub feed is what makes the walk deterministic",
  );
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  await expect(
    page.getByRole("button", { name: "Back", exact: true }),
  ).toHaveCount(0);

  await page.getByText("jason", { exact: true }).first().click();
  await page.waitForURL(/\/c\//);

  const back = page.getByRole("button", { name: "Back", exact: true });
  await expect(back).toBeVisible();

  await back.click();
  await expect.poll(async () => new URL(page.url()).pathname).toBe("/");
});

test("a cold link has no back arrow, because back would leave the app", async ({
  page,
}) => {
  stubOnly("same feed");
  await page.goto(`/c/${CHARACTER}`);
  await page.waitForLoadState("networkidle");
  await expect(
    page.getByRole("button", { name: "Back", exact: true }),
  ).toHaveCount(0);
});

/**
 * **Every tile is a link, so the browser's own gestures work on it.**
 *
 * Command-click, middle-click, "open in new tab", "copy link address" — a
 * `<button>` offers none of them, and the media grid was built out of buttons,
 * so the one place in this app most worth opening in a second tab was the one
 * place you could not. The fix is an `href` the router intercepts on a plain
 * click only.
 *
 * Asserted as markup rather than by driving a modifier-click: what a real
 * command-click does is the browser's business, and a test that opened a tab
 * would be checking Chromium. What this can check is that we handed it
 * something to work with.
 */
test("media tiles are links, so a modified click can leave the page", async ({
  page,
}) => {
  stubOnly("the stub feed is what makes the grid deterministic");
  // Home's Recent grid, which the reel fixture fills — a character's Files tab
  // needs a tab click to reach and this is about the tile, not the route.
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const linked = page.locator('main a[href*="/o/"]');
  await expect.poll(async () => linked.count()).toBeGreaterThan(0);

  // The address has to be the same place a plain click goes, or the two
  // gestures land differently and the link is worse than no link.
  const href = await linked.first().getAttribute("href");
  expect(href).toMatch(/^\/o\/node-/);
});

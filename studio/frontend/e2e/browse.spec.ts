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

/** The character's own label — not the id its root FOLDER is named after. */
const CHARACTER_NAME = fixture<{ name: string }>("character").name;

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
  await expect(page.getByText(/0 sent · 54 files/)).toBeVisible();
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

/**
 * **An entity's root folder is stored under the entity id**, on purpose: two
 * characters called the same thing would otherwise collide on the folder tree's
 * own name uniqueness. So its crumb had a stored name nobody recognises — a
 * 41-character UUID that wrapped onto two lines at 390px — and the Files tab
 * passes the character's name down to draw in its place.
 *
 * Display only. `prefix` — what Copy prefix yields and what `GET /api/resolve`
 * takes — is still built from stored names, so this changed the label and not
 * the address.
 *
 * **The fixture carries the id-shaped folder name for this reason.** It was
 * captured before slugs were removed and still said `jason`, against which this
 * spec passes even with the label wired to nothing at all.
 */
test("the Files tab names its boundary crumb after the character", async ({
  page,
}) => {
  stubOnly("the captured tree is what makes the crumb deterministic");
  await page.goto(`/c/${CHARACTER}?tab=files`);

  // The LAST one: `PageBar` draws a breadcrumb of its own above the tabs.
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" }).last();
  await expect(crumbs).toHaveText(CHARACTER_NAME);
  await expect(crumbs).not.toContainText(CHARACTER);
});

/**
 * **Media is the second question a folder gets asked**, and it was only
 * answerable by walking. A character's pictures are spread across `reference/`,
 * `corpus/`, `seed/` and `archive/` by convention — none of it enforced — so
 * "show me everything of this character" meant opening four folders in turn and
 * holding the result in your head.
 *
 * The view sends `kind=image,video`, which `getFolder` sends with `depth=all`,
 * so it is the tag filter's own trick in the other vocabulary: narrowing turns
 * a readdir into a search of the subtree. Folders and text drop out of the
 * result rather than being hidden by a branch in the render.
 *
 * `?view=` rather than component state, so the answer is a link.
 */
test("Media shows the whole subtree's pictures, and Folders comes back", async ({
  page,
}) => {
  stubOnly("the captured tree is what makes the two listings differ");
  await page.goto(`/c/${CHARACTER}?tab=files`);

  const folders = page.getByRole("heading", { name: "Folders" });
  const media = page.getByRole("heading", { name: /Photos & video/ });
  await expect(folders).toBeVisible();

  await page.getByRole("button", { name: "Media", exact: true }).click();
  await expect(media).toBeVisible();
  // The folders are not hidden — they are not in the answer.
  await expect(folders).toHaveCount(0);
  await expect(page).toHaveURL(/view=media/);
  await expect(
    page.getByText("Searching this folder and everything under it."),
  ).toBeVisible();

  // Both ways, because a one-way switch is a trap: the folder chips above still
  // scope where you are standing, and getting back to them must not need a
  // reload.
  await page.getByRole("button", { name: "Folders", exact: true }).click();
  await expect(folders).toBeVisible();
  await expect(media).toHaveCount(0);
});

/**
 * **A Media tile has to OPEN**, and it did not.
 *
 * The listing behind the view searches the branch, so the tile is usually a
 * file in some subfolder — while the address the tile carried said `in=f:<this
 * folder>`, which makes the viewer re-read that one folder, one level deep, to
 * find the neighbours. The file was not in it. What a person got for clicking a
 * picture was "No images or videos here", and where the folder did hold media
 * of its own, something else opened instead.
 *
 * A deep listing addresses its tiles `in=recursive:` now — the same walk that
 * produced them. This spec is worth its length because both halves are silent:
 * the message is a plausible empty state, and the wrong-file case looks like a
 * click that landed badly.
 */
test("a tile in Media opens the file it shows", async ({ page }) => {
  stubOnly("the captured tree is what puts the media below this folder");
  await page.goto(`/c/${CHARACTER}?tab=files`);

  await page.getByRole("button", { name: "Media", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Photos & video/ })).toBeVisible();

  // The context is the branch walk, not the folder — which is the fix, and it
  // is checked on the href as well as by clicking so a regression names itself.
  const tile = page.locator('main a[href*="/o/"]').first();
  await expect(tile).toHaveAttribute("href", /in=recursive/);

  await tile.click();
  await expect(page).toHaveURL(/\/o\/node-/);
  // The viewer, on a file: the neighbours strip and the details region only
  // render once there is something to draw.
  await expect(page.getByLabel("Neighbours")).toBeVisible();
  await expect(page.getByRole("region", { name: "File details" })).toBeVisible();
  await expect(page.getByText("No images or videos yet.")).toHaveCount(0);
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
 * **`PageBar` draws no back arrow, on any page.**
 *
 * It used to — an `IconButton` shown whenever `location.key !== "default"`,
 * so the same page laid out differently opened cold versus opened from a
 * list. The browser's own Back already answers "where did I come from"; a
 * crumb answers "where am I", which Back cannot — so the arrow is gone
 * everywhere rather than conditionally somewhere.
 *
 * `exact: true` is not decoration: Playwright matches an accessible name as a
 * case-insensitive SUBSTRING, and a character's body-angle stills are named
 * "…back…", so a loose locator matches four tiles in the Recent grid and the
 * test fails on a page that is behaving perfectly.
 */
test("there is no back arrow, cold or navigated to", async ({ page }) => {
  stubOnly("the stub feed is what makes the walk deterministic");
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(
    page.getByRole("button", { name: "Back", exact: true }),
  ).toHaveCount(0);

  await page.getByText("jason", { exact: true }).first().click();
  await page.waitForURL(/\/c\//);
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

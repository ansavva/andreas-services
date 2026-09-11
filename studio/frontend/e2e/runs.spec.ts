/**
 * The feed, the opened run, running one, running one again, and filing an
 * output as identity.
 *
 * **Three flows here spend money or change what a character IS**, and every
 * one of them is a SEQUENCE of calls rather than a single request. The unit
 * suite pins each sequence against mocked modules; what only a browser can say
 * is that the real components, wired to the real router and the real API
 * client, still make those calls in that order against a stub that answers the
 * way the API does.
 *
 * **Two properties here are safety properties and not features.**
 *
 * - An armed button's FIRST press must send nothing. It is the whole of hard
 *   rule #2 as this app implements it: the confirmation lives in the button, so
 *   a button that fired on the first press would be a spend with no yes. Every
 *   armed control below is asserted against a request log, not against its own
 *   label — a label can say "press again" while the handler has already run.
 * - A promotion must attach the COPY. Attaching the original would make a run's
 *   own output the character's identity, which is the exact thing the copy
 *   exists to prevent, and nothing on the screen would look different.
 *
 * Every `/api/**` is answered from fixtures captured off the real API — see
 * `support/api.ts`, and `fixtures/capture.py` for why the ones these specs need
 * come from a stack that has been worked in rather than from the published
 * seed. `project-runs-feed.json` holds two of that project's four runs — the
 * draft and the succeeded image run — which is what the feed draws here.
 */
import { expect, test } from "@playwright/test";

import {
  CHARACTER,
  COPY,
  CREATED_RUN,
  DRAFT_RUN,
  IMAGE_RUN,
  IMAGE_RUN_REQUEST,
  LIBRARY,
  OUTPUT,
  PROJECT,
  REFERENCE_POOL,
  RUN_ID,
  RUN_PROJECT,
  CHARACTER_ROOT,
  fixture,
  stubApi,
} from "./support/api";
import { escaped, log, spell, wrote } from "./support/calls";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

/**
 * Per-spec, never at module level.
 *
 * A module-level `test.skip` skips the file, which is how a suite reports green
 * having run nothing — the same shape as the collection hook that once skipped
 * all 373 backend tests and exited 0.
 */
function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

/** The opened run — the lightbox over the feed. */
const lightbox = (page: Page) => page.getByRole("dialog", { name: "Run" });

/** The feed row holding one run — found by the tile that opens it. */
function rowOf(page: Page, output: string) {
  return page.locator("article").filter({ has: page.getByRole("button", { name: `Open ${output}` }) });
}

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

/* -------------------------------------------------------------------------
 * The feed
 * ---------------------------------------------------------------------- */

/**
 * **The project opens on the feed, and the feed is the runs.**
 *
 * One row per run from `?view=feed`, the prompt search on the feed itself and
 * in the address. The `List | Grid` toggle the Runs tab used to carry is gone
 * with the tab it sat on: Grid was the file browser over `runs/`, which is
 * Files' question one tab over.
 */
test("the project opens on the feed, one row per run, with a prompt search in the address", async ({
  page,
}) => {
  stubOnly("the feed fixture is a projection of two captured runs");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  await expect(page.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("article")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Grid", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "List", exact: true })).toHaveCount(0);

  const feed = calls.find((call) => call.path.endsWith("/api/runs") && call.query.get("view") === "feed");
  expect(feed).toBeDefined();
  expect(feed!.query.get("project")).toBe(PROJECT);
  expect(feed!.query.get("include")).toBe("drafts");

  // The search: typed, applied on Enter, answered by the stub the way the API
  // answers `?q=` — the prompt's string leaves — and one row survives.
  const search = page.getByRole("textbox", { name: "Search prompts" });
  await search.fill("studio photograph");
  await search.press("Enter");
  await expect(page).toHaveURL(/[?&]q=studio\+photograph/);
  await expect(page.locator("article")).toHaveCount(1);
  expect(wrote(calls)).toEqual([]);
});

/**
 * **A run in flight is polled by ITSELF, and the feed is not re-read.**
 *
 * The feed used to carry the `refetchInterval`, and refetching an infinite
 * query re-runs every page it holds — so watching one prediction land cost a
 * `?view=feed` call per loaded page every five seconds, each re-reading an
 * envelope per row and re-signing every send and output on it. What replaced it
 * is `useRunWatch`: one `GET /api/runs/<id>` per row still out, and the record
 * that reports the landing carries the outputs, so the page it sits on is
 * patched rather than re-read.
 *
 * The claim is a COUNT, which is the only way to see this from outside: the
 * listing is asked for once and the run is asked for repeatedly. It waits on
 * the second poll rather than on a clock, so nothing here depends on how fast
 * the machine is — only on the interval eventually elapsing.
 */
test("a run in flight polls itself, and the feed is read once", async ({
  page,
}) => {
  stubOnly("the feed fixture is a projection of two captured runs");
  const calls = log(page);

  // The captured succeeded run, put back into flight — and landing again once
  // the poll has been seen twice.
  const feed = fixture<{ runs: Array<Record<string, unknown>> }>(
    "project-runs-feed",
  );
  const landed = feed.runs[1]!;
  const flying = {
    ...landed,
    status: "running",
    outputs: [],
    thumb: null,
    completed: null,
  };
  const record = fixture<Record<string, unknown>>("run-image");
  let done = false;

  // Registered after `stubApi`, so these win: Playwright matches the most
  // recently added route first.
  await page.route(
    (url) => url.pathname.endsWith("/api/runs"),
    (route, request) =>
      new URL(request.url()).searchParams.get("view") === "feed"
        ? route.fulfill({
            contentType: "application/json",
            body: JSON.stringify({ runs: [flying], cursor: null }),
          })
        : route.fallback(),
  );
  await page.route(
    (url) => url.pathname === `/api/runs/${landed.id as string}`,
    (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          done ? record : { ...record, status: "running", outputs: [] },
        ),
      }),
  );

  await page.goto(`/p/${PROJECT}`);
  await expect(page.getByTestId("in-flight-tile").first()).toBeVisible();

  const feedCalls = () =>
    calls.filter(
      (call) => call.path.endsWith("/api/runs") && call.query.get("view") === "feed",
    ).length;
  const runCalls = () =>
    calls.filter((call) => call.path === `/api/runs/${landed.id as string}`).length;

  // The interval fired at least once on top of the first read.
  await expect.poll(runCalls, { timeout: 20_000 }).toBeGreaterThan(1);
  expect(feedCalls()).toBe(1);

  // And the landing arrives on that same per-run poll: the outputs draw, and
  // the listing is still never asked again.
  done = true;
  await expect(page.getByRole("button", { name: "Open Output 1 of 1" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("in-flight-tile")).toHaveCount(0);
  expect(feedCalls()).toBe(1);
  expect(wrote(calls)).toEqual([]);
});

/* -------------------------------------------------------------------------
 * The one act: arm, then run
 * ---------------------------------------------------------------------- */

test("one press on Run arms it and sends nothing", async ({ page }) => {
  stubOnly("the second press would submit a real generation");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}?tab=runs`);

  // The draft's row: nothing came out of it, so its tile grid is empty and
  // its one spending control is Run.
  const run = page.getByRole("button", { name: "Run", exact: true });
  await expect(run).toBeVisible();
  await run.click();

  // The label changing is not the property. The property is that nothing went.
  await expect(page.getByRole("button", { name: /Press again/ })).toBeVisible();
  expect(wrote(calls)).toEqual([]);
});

test("the second press submits, and calls nothing before it", async ({
  page,
}) => {
  stubOnly("this is the call that spends");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}?tab=runs`);

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.getByRole("button", { name: /Press again/ }).click();

  // One write. There is no approve step (decision 2026-09-04): the press is the
  // act, and the API takes a draft straight to the provider.
  await expect
    .poll(() => spell(wrote(calls)))
    .toEqual([`POST /api/runs/${DRAFT_RUN}/submit`]);
  expect(escaped(calls, page)).toEqual([]);
});

/* -------------------------------------------------------------------------
 * Rerun
 * ---------------------------------------------------------------------- */

test("Rerun takes two presses, the first sends nothing, and the second opens the new attempt", async ({
  page,
}) => {
  stubOnly("the second press submits a real generation");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}?tab=runs`);

  const row = rowOf(page, "Output 1 of 1");
  const rerun = row.getByRole("button", { name: "Rerun", exact: true });
  await expect(rerun).toBeVisible();

  await rerun.click();
  await expect(row.getByRole("button", { name: /Press again/ })).toBeVisible();
  // **The safety property.** A re-run creates a run and submits it in one
  // gesture, so a button that fired on the first press would bill on a stray
  // click with no sentence read.
  expect(wrote(calls)).toEqual([]);

  await row.getByRole("button", { name: /Press again/ }).click();

  // Create, submit — then the address follows the new attempt, opened over the
  // feed, so the previous one keeps its outputs and the feed is still under it.
  await page.waitForURL(new RegExp(`/p/${PROJECT}/r/${CREATED_RUN}`));
  expect(spell(wrote(calls))).toEqual([
    "POST /api/runs",
    `POST /api/runs/${CREATED_RUN}/submit`,
  ]);
  await expect(lightbox(page)).toBeVisible();

  // The body is the source run's, copied rather than reconstructed: same model,
  // same ordered images. Byte-identical payloads are what keep the duplicate
  // check honest. Every one of them was answered by the stub. See `escaped`.
  expect(escaped(calls, page)).toEqual([]);

  const created = wrote(calls)[0]!.body;
  expect(created).toMatchObject({
    project: PROJECT,
    kind: "image",
    model: "openai/gpt-image-2",
  });
  expect((created.sends as unknown[]).length).toBeGreaterThan(0);
});

test("Rerun is offered on a finished run and Run on a draft, never both on one", async ({
  page,
}) => {
  stubOnly("the fixtures are what make the two states side by side");
  await page.goto(`/p/${PROJECT}?tab=runs`);

  const finished = rowOf(page, "Output 1 of 1");
  await expect(finished.getByRole("button", { name: "Rerun", exact: true })).toBeVisible();
  await expect(finished.getByRole("button", { name: "Run", exact: true })).toHaveCount(0);

  // A run row records one submission, so a draft offers Run and a submitted
  // run only the offer of a second attempt.
  await expect(page.getByRole("button", { name: "Run", exact: true })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Rerun", exact: true })).toHaveCount(1);
});

/* -------------------------------------------------------------------------
 * The opened run
 * ---------------------------------------------------------------------- */

/**
 * **A tile opens the run in place, over the feed.** The address gains the run
 * and keeps the tab; the sidebar collapses to its rail; Esc puts both back.
 */
test("a tile opens the run in a lightbox, collapses the rail, and Esc returns to the feed", async ({
  page,
}) => {
  stubOnly("the feed fixture is what the tile is drawn from");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/p/${PROJECT}?tab=runs`);
  await expect(page.getByRole("button", { name: "Collapse sidebar" })).toBeVisible();

  await page.getByRole("button", { name: "Open Output 1 of 1" }).click();

  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}/r/${IMAGE_RUN}\\?tab=runs$`));
  await expect(lightbox(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  // The rail draws the run: its prompt, its status, its model, its cast.
  const rail = lightbox(page).getByRole("complementary", { name: "Run details" });
  // **`toBeVisible`, and it is not a formality.** The prompt scrolls, which
  // makes it a scroll container, which gives it `min-height: 0` — so it was the
  // one flex child a rail taller than the lightbox could shrink, and it shrank
  // to zero on every opened run. The text was in the DOM the whole time; only
  // its box was gone, which is exactly what this assertion reads and
  // `toHaveText` would not.
  await expect(rail.getByText(/A studio photograph of the man/)).toBeVisible();
  await expect(rail.getByText("succeeded")).toBeVisible();
  await expect(rail.getByText("openai/gpt-image-2")).toBeVisible();
  await expect(rail.getByRole("link", { name: /jason/ })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}\\?tab=runs$`));
  await expect(lightbox(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Collapse sidebar" })).toBeVisible();
});

/**
 * **The Request row is what shows the payload, and it fetches nothing until
 * asked.** Three documents, each read through `GET /api/nodes/<id>/text` when
 * its own row is pressed, and shown as text — studio decodes none of them.
 */
test("the Request row loads a payload document only when it is pressed", async ({
  page,
}) => {
  stubOnly("the payload node ids are the captured run's");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(lightbox(page)).toBeVisible();

  const text = () => calls.filter((call) => call.path.endsWith("/text"));
  // `exact`: the collapsed row's own trigger names all three documents. The
  // collapsed panel is `inert`, which Playwright does not count as hidden, so
  // what is asserted is the row's state and that nothing has been fetched.
  const row = lightbox(page).getByRole("button", { name: /^Request/ });
  const document = lightbox(page).getByRole("button", { name: "request.json", exact: true });
  await expect(row).toHaveAttribute("aria-expanded", "false");
  expect(text()).toEqual([]);

  await row.click();
  await expect(row).toHaveAttribute("aria-expanded", "true");
  await expect(document).toBeVisible();
  expect(text()).toEqual([]);

  await document.click();
  await expect.poll(() => text().map((call) => call.path)).toEqual([
    `/api/nodes/${IMAGE_RUN_REQUEST}/text`,
  ]);
  await expect(lightbox(page).getByText('"shot": "e2e"')).toBeVisible();
  expect(wrote(calls)).toEqual([]);
});

/* -------------------------------------------------------------------------
 * Copying an output into a character
 * ---------------------------------------------------------------------- */

test("copying an output puts the COPY in the chosen folder, and tags that", async ({
  page,
}) => {
  stubOnly("it would write a picture into the dev character");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(lightbox(page)).toBeVisible();

  // Scoped to the lightbox: the feed's tiles under it carry the same action in
  // their own menus.
  const trigger = lightbox(page).getByRole("button", {
    name: "Copy into a character",
    exact: true,
  });
  const submit = page.getByRole("button", { name: "Copy", exact: true });

  await expect(submit).toHaveCount(0);
  await trigger.click();
  await expect(page.getByRole("heading", { name: /^Copy into / })).toBeVisible();

  // The run names one character, so it is preselected — two would be a choice
  // this cannot make, and one is the case that should cost no clicks. Scoped
  // to the drawer: the feed's filter under it has a Character select too.
  const drawer = page.getByRole("dialog").filter({ has: submit });
  await expect(
    drawer.getByRole("combobox", { name: "Character", exact: true }),
  ).toContainText("jason");

  // **The folder is chosen, not conventional.** There is no group and no pool
  // this app creates: the picker walks the character's own tree and the id it
  // hands back is where the copy goes.
  await expect(submit).toBeDisabled();
  await drawer.getByRole("button", { name: /Choose a folder/ }).click();
  const picker = page.getByRole("dialog").filter({ hasText: "Copy" }).last();
  await picker.getByRole("button", { name: "reference" }).click();
  await picker.getByRole("button", { name: /^Copy here/ }).click();
  await expect(submit).toBeEnabled();

  // **A tag, because tagging is now the only way a picture becomes identity.**
  // `default` used to be written on every promotion; nothing writes it now, so
  // this is a person saying it in as many words.
  const tagBox = drawer.getByRole("textbox", { name: "Add a tag" });
  await tagBox.fill("default");
  await tagBox.press("Enter");
  // The suggestion list stays open over the form until it is dismissed.
  await tagBox.press("Escape");

  // Everything before the press is setup. What the order assertion is about is
  // what the press itself does.
  calls.length = 0;
  await submit.click();
  await expect(page.getByText(/Copied into/)).toBeVisible();

  expect(escaped(calls, page)).toEqual([]);

  const promotion = calls.filter((call) =>
    /\/api\/(nodes\/copy$|nodes\/node-)/.test(call.path),
  );
  expect(spell(promotion)).toEqual([
    // The bytes, into the folder that was picked.
    "POST /api/nodes/copy",
    // Then the copy is described — and only because a tag was typed.
    `PATCH /api/nodes/${COPY}`,
  ]);

  // The run's own output, into the chosen folder — not by name.
  const copy = promotion[0]!.body;
  expect(copy.ids).toEqual([OUTPUT.node]);
  expect(copy.destination).toBe(REFERENCE_POOL);

  // **The whole point.** What is described is the copy the destination made,
  // not the run's own output — two blobs with independent lifetimes, so
  // re-tagging or deleting the copy later cannot reach back into the run.
  expect(promotion[1]!.path.endsWith(`/api/nodes/${COPY}`)).toBe(true);
  expect(promotion[1]!.path.endsWith(OUTPUT.node)).toBe(false);
  expect(promotion[1]!.body.tags).toEqual(["default"]);
});

test("only an image output offers to be copied into a character", async ({ page }) => {
  stubOnly("the run fixtures are what put an image and a clip side by side");
  const promote = () =>
    lightbox(page).getByRole("button", { name: "Copy into a character", exact: true });

  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(lightbox(page)).toBeVisible();
  await expect(promote()).toHaveCount(1);

  // The synthesised run in `support/api.ts` outputs the MP4. What a character
  // is kept and matched against is pictures, so a clip is not offered —
  // and this is the same lightbox, the same grid, and one different content
  // type. Its project is not in any feed fixture, so the row is drawn off the
  // record: the cold-link path.
  await page.goto(`/p/${RUN_PROJECT}/r/${RUN_ID}`);
  await expect(lightbox(page)).toBeVisible();
  await expect(lightbox(page).locator("video")).toHaveCount(1);
  await expect(promote()).toHaveCount(0);
});

/* -------------------------------------------------------------------------
 * Pressing the picture
 * ---------------------------------------------------------------------- */

/**
 * **A press on an output's picture opens the run, wherever on it the press
 * lands.**
 *
 * Two faults stacked into one: the tile stretched to whatever the plan beside
 * it was tall, so most of it was black rather than picture, and the hover
 * controls over it were `opacity-0` with their pointer events left on. A press
 * low on a still therefore ran Animate or Upscale on it, and one in the corner
 * started a download — which navigates the window, so the app came back cold.
 * On a touch screen, where the hover state may never arrive, that was every
 * press the tile got.
 *
 * Asserted through the browser's own hit-testing (`click({ position })`), which
 * is the only thing that can see an invisible control over a picture: in jsdom
 * there is no cascade and the handler on the tile is reached either way.
 */
test("a press at the foot of an output opens the run rather than a control hidden over it", async ({
  page,
}) => {
  stubOnly("the feed fixture is what the tile is drawn from");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/p/${PROJECT}?tab=runs`);

  const tile = page.getByRole("button", { name: "Open Output 1 of 1" });
  const box = (await tile.boundingBox())!;

  // The tile is the picture and nothing else: it used to sit at the top of a
  // frame stretched to the height of the plan column, and the slack was black.
  const frame = (await tile.locator("..").boundingBox())!;
  expect(frame.height).toBeLessThan(box.height + 8);

  // Low and to the left: the hover controls are a strip along the bottom
  // RIGHT of the picture, and a hover turns them live, so this is the press
  // that used to land on Animate.
  await tile.click({ position: { x: 8, y: box.height - 20 } });
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}/r/${IMAGE_RUN}`));
  await expect(lightbox(page)).toBeVisible();
});

/**
 * **Folder is a link, and a link inside the app is the router's.**
 *
 * It was a bare `<a href="/o/…">`, so the one control that says "show me where
 * this lives" also threw the session away: the bundle re-ran, every query
 * started empty and every picture on the screen was fetched again. The probe
 * is a value on `window` — a full document load is the only thing that can
 * take it away.
 */
test("Folder navigates in the app rather than reloading it", async ({ page }) => {
  stubOnly("the folder link is built from the captured run's outputs");
  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(lightbox(page)).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { probe?: string }).probe = "kept";
  });
  await lightbox(page).getByRole("link", { name: "Folder" }).click();

  await expect(page).toHaveURL(/\/f\//);
  expect(
    await page.evaluate(() => (window as unknown as { probe?: string }).probe),
  ).toBe("kept");
});

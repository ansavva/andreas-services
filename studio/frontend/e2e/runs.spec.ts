/**
 * Authoring a run, running one again, and filing an output as identity.
 *
 * **These three flows are the only ones in the app that spend money or change
 * what a character IS**, and every one of them is a SEQUENCE of calls rather
 * than a single request. The unit suite pins each sequence against mocked
 * modules; what only a browser can say is that the real components, wired to
 * the real router and the real API client, still make those calls in that order
 * against a stub that answers the way the API does.
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
 * seed.
 */
import { expect, test, type Page } from "@playwright/test";

import {
  CHARACTER,
  COPY,
  CREATED_RUN,
  DRAFT_RUN,
  IMAGE_RUN,
  LIBRARY,
  OUTPUT,
  PROJECT,
  REFERENCE_POOL,
  RUN_ID,
  CHARACTER_ROOT,
  stubApi,
} from "./support/api";
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

/** One call the app made, as this file wants to read it back. */
interface Call {
  method: string;
  /** Kept so a spec can prove the call was served by the stub, not by :8000. */
  origin: string;
  path: string;
  query: URLSearchParams;
  body: Record<string, unknown>;
}

/**
 * Every `/api` call, in the order the browser made them.
 *
 * Registered before the first navigation, because a listener attached
 * afterwards cannot have seen what it is about to assert on — the same mistake
 * an early version of `browse.spec.ts`'s escape check made.
 */
function log(page: Page): Call[] {
  const calls: Call[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return;
    let body: Record<string, unknown> = {};
    try {
      body = (request.postDataJSON() ?? {}) as Record<string, unknown>;
    } catch {
      /* a GET, or a write with no JSON body */
    }
    calls.push({
      method: request.method(),
      origin: url.origin,
      path: url.pathname,
      query: url.searchParams,
      body,
    });
  });
  return calls;
}

const wrote = (calls: Call[]) => calls.filter((call) => call.method !== "GET");
const spell = (calls: Call[]) =>
  calls.map((call) => `${call.method} ${call.path}`);

/**
 * Calls that went somewhere other than the page's own origin.
 *
 * **`npm run e2e` builds and previews on :4173 and must not depend on a dev
 * server.** A developer usually has `dev-up.sh` running while writing these, so
 * a spec that only passed because :8000 happened to be up would pass locally and
 * fail in CI — where there is no stack at all. This is that assumption made
 * checkable inside the flows that write.
 */
function escaped(calls: Call[], page: Page): string[] {
  const here = new URL(page.url()).origin;
  return calls
    .filter((call) => call.origin !== here)
    .map((call) => `${call.origin}${call.path}`);
}

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

/* -------------------------------------------------------------------------
 * Authoring a new run
 * ---------------------------------------------------------------------- */

test("the composer strip makes a draft and lands in its editor", async ({
  page,
}) => {
  stubOnly("it would create a real draft in the dev stack");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}?tab=runs`);

  // Closed until asked for, and it opens in the place the button stood.
  await page.getByRole("button", { name: "New run" }).click();

  const kinds = page.getByRole("group", { name: "Kind" });
  // `exact`, because the runs filter above the strip has a Model box of its own
  // — and the two mean opposite things: one narrows a listing, the other picks
  // what a new run will be rendered by.
  const model = page.getByRole("combobox", { name: "Model", exact: true });

  // The kind filters the model list, which is the whole reason the toggle is
  // beside the Select rather than somewhere else: a video model offered under
  // `kind: image` is a 400 at submit, after the plan has been written.
  await kinds.getByRole("button", { name: "Video" }).click();
  await model.click();
  await expect(page.getByRole("option", { name: "seedance" })).toBeVisible();
  await expect(page.getByRole("option", { name: "gpt-image-2" })).toHaveCount(0);
  await page.keyboard.press("Escape");

  await kinds.getByRole("button", { name: "Image" }).click();
  await model.click();
  await page.getByRole("option", { name: "gpt-image-2", exact: true }).click();

  // Nothing has been created yet: choosing a model is not creating a run, and a
  // strip that wrote a row per keystroke would fill the project with drafts.
  expect(wrote(calls)).toEqual([]);

  await page.getByRole("button", { name: "Create draft" }).click();

  await page.waitForURL(new RegExp(`/p/${PROJECT}/r/${CREATED_RUN}$`));
  const created = wrote(calls);
  expect(spell(created)).toEqual(["POST /api/runs"]);
  // The Replicate `owner/name`, never the registry key — `POST /api/runs`
  // records the model the provider is called by.
  expect(created[0]!.body).toMatchObject({
    project: PROJECT,
    kind: "image",
    model: "openai/gpt-image-2",
    engine: "studio-media-gpt-image-2",
  });

  // Landed IN the editor rather than on the read view of an empty plan, which
  // is what `state.editing` buys and why it is router state and not a query
  // parameter.
  await expect(page.getByText("Editing the plan")).toBeVisible();
  // The live schema drew the params form: `aspect_ratio` is an `allOf` naming a
  // component, so its presence is also the `$ref` resolution working end to end.
  await expect(page.getByLabel("aspect_ratio")).toBeVisible();
});

/* -------------------------------------------------------------------------
 * The one act: arm, then run
 * ---------------------------------------------------------------------- */

/**
 * **The Runs tab used to offer a Grid beside the List, and the pair is gone.**
 *
 * Grid drew the file browser scoped to the project's `runs/` folder in Media
 * view — a run's OUTPUTS, which is Files' question one tab over on exactly the
 * same folder, not the Runs tab's. What replaced the assertion above is simply
 * that the list — status, model, cost, the plan behind it — is what this tab
 * shows, with no toggle and no `?runs=` beside it.
 */
test("the Runs tab is the list, with no reading to switch away from", async ({
  page,
}) => {
  await page.goto(`/p/${PROJECT}?tab=runs`);

  await expect(page.getByLabel("Status")).toBeVisible();
  await expect(page.getByRole("button", { name: "Grid", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "List", exact: true })).toHaveCount(0);
  await expect(page).not.toHaveURL(/runs=/);
});

test("one press on Run arms it and approves nothing", async ({ page }) => {
  stubOnly("the second press would submit a real generation");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${DRAFT_RUN}`);

  const run = page.getByRole("button", { name: "Run", exact: true });
  await expect(run).toBeVisible();
  await run.click();

  // The label changing is not the property. The property is that nothing went.
  await expect(
    page.getByRole("button", { name: /Press again/ }),
  ).toBeVisible();
  expect(wrote(calls)).toEqual([]);
});

test("the second press approves and then submits, in that order", async ({
  page,
}) => {
  stubOnly("this is the call that spends");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${DRAFT_RUN}`);

  const run = page.getByRole("button", { name: "Run", exact: true });
  await run.click();
  await page.getByRole("button", { name: /Press again/ }).click();

  // Approve BEFORE submit, always: the API refuses a submission that is not
  // approved, and the digest is what ties the yes to this exact payload.
  await expect
    .poll(() => spell(wrote(calls)))
    .toEqual([
      `POST /api/runs/${DRAFT_RUN}/approve`,
      `POST /api/runs/${DRAFT_RUN}/submit`,
    ]);
  expect(wrote(calls)[0]!.body.digest).toBeTruthy();
});

/* -------------------------------------------------------------------------
 * Run again
 * ---------------------------------------------------------------------- */

test("Run again takes two presses, and the first sends nothing", async ({
  page,
}) => {
  stubOnly("the second press submits a real generation");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);

  const again = page.getByRole("button", { name: "Run again", exact: true });
  await expect(again).toBeVisible();

  await again.click();
  await expect(
    page.getByRole("button", { name: /Press again/ }),
  ).toBeVisible();
  // **The safety property.** A re-run creates a run and submits it in one
  // gesture, so a button that fired on the first press would bill on a stray
  // click with no sentence read.
  expect(wrote(calls)).toEqual([]);

  await page.getByRole("button", { name: /Press again/ }).click();

  // Create, approve, submit — then the address follows the new attempt, so the
  // previous one keeps its outputs and Back returns to it.
  await page.waitForURL(new RegExp(`/p/${PROJECT}/r/${CREATED_RUN}$`));
  expect(spell(wrote(calls))).toEqual([
    "POST /api/runs",
    `POST /api/runs/${CREATED_RUN}/approve`,
    `POST /api/runs/${CREATED_RUN}/submit`,
  ]);

  // The body is the source run's, copied rather than reconstructed: same model,
  // same ordered images. Byte-identical payloads are what keep the duplicate
  // check honest.
  // Every one of them was answered by the stub. See `escaped`.
  expect(escaped(calls, page)).toEqual([]);

  const created = wrote(calls)[0]!.body;
  expect(created).toMatchObject({
    project: PROJECT,
    kind: "image",
    model: "openai/gpt-image-2",
  });
  expect((created.sends as unknown[]).length).toBeGreaterThan(0);
});

test("Run again is offered on a submitted run and not on a draft", async ({
  page,
}) => {
  stubOnly("the fixtures are what make the two states side by side");
  await page.goto(`/p/${PROJECT}/r/${DRAFT_RUN}`);
  await expect(page.getByRole("button", { name: /Run again/ })).toHaveCount(0);

  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(page.getByRole("button", { name: /Run again/ })).toBeVisible();
  // A run row records one submission, so there is no Run on a submitted run to
  // press by mistake — only the offer of a second attempt.
  await expect(
    page.getByRole("button", { name: "Run", exact: true }),
  ).toHaveCount(0);
});

/* -------------------------------------------------------------------------
 * Promote to reference
 * ---------------------------------------------------------------------- */

test("promoting copies into the pool and TAGS the copy", async ({
  page,
}) => {
  stubOnly("it would write a reference into the dev character");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);

  // **They used to share the word `Promote`** — the caption-row disclosure and
  // the form's submit — and were told apart by `aria-expanded`. The form is a
  // drawer named for where the picture is going now, and its submit says what
  // it adds, so the two no longer collide and each is found by its own name.
  const trigger = page.getByRole("button", { name: "Promote", exact: true });
  const submit = page.getByRole("button", { name: "Add reference", exact: true });

  await expect(submit).toHaveCount(0);
  await trigger.click();
  await expect(page.getByText(/Add to .+ references/)).toBeVisible();
  await expect(submit).toHaveCount(1);
  // The run names one character, so it is preselected — two would be a choice
  // this cannot make, and one is the case that should cost no clicks.
  await expect(
    page.getByRole("combobox", { name: "Character", exact: true }),
  ).toContainText("jason");

  // Everything before the press is setup. What the order assertion is about is
  // what the press itself does.
  calls.length = 0;
  await submit.click();
  await expect(
    page.getByText(/Added to .+ references/),
  ).toBeVisible();

  expect(escaped(calls, page)).toEqual([]);

  const promotion = calls.filter((call) =>
    /\/api\/(characters\/|nodes$|nodes\/copy$|nodes\/node-)/.test(call.path),
  );
  expect(spell(promotion)).toEqual([
    // The character, for its root folder.
    `GET /api/characters/${CHARACTER}`,
    // **One folder ensured, not two.** The group was a `<group>/` subfolder and
    // a column on a row; it is a tag, so only `reference/` is resolved.
    "GET /api/nodes",
    // Only then the bytes, and only then the identity — which is a tag written
    // onto the COPY, never onto the run's own output.
    "POST /api/nodes/copy",
    `PATCH /api/nodes/${COPY}`,
  ]);

  // **One listing, of the root.** A promotion used to resolve `reference/` and
  // then a `<group>/` folder inside it, because a group was a place as well as a
  // column. It is only a tag, so the copy lands in the pool and there is nothing
  // else to find or create. `under`, where the folder listing said `node`.
  expect(promotion[1]!.query.get("under")).toBe(CHARACTER_ROOT);

  // The run's own output, into the pool — not by name.
  const copy = promotion[2]!.body;
  expect(copy.ids).toEqual([OUTPUT.node]);
  expect(copy.destination).toBe(REFERENCE_POOL);

  // **The whole point.** The tag lands on the copy the destination made, not on
  // the run's own output — two blobs with independent lifetimes, so untagging or
  // deleting the promoted image later cannot reach back into the run.
  expect(promotion[3]!.path.endsWith(`/api/nodes/${COPY}`)).toBe(true);
  expect(promotion[3]!.path.endsWith(OUTPUT.node)).toBe(false);
  expect(promotion[3]!.body.tags).toEqual(["default", "unsorted"]);
});

test("only an image output offers to become a reference", async ({ page }) => {
  stubOnly("the run fixtures are what put an image and a clip side by side");
  const promote = page.getByRole("button", { name: "Promote", exact: true });

  await page.goto(`/p/${PROJECT}/r/${IMAGE_RUN}`);
  await expect(promote).toHaveCount(1);

  // The synthesised run in `support/api.ts` outputs the MP4. A reference is a
  // picture every later render is checked against, so a clip cannot be one —
  // and this is the same page, the same panel, and one different content type.
  await page.goto(`/p/${PROJECT}/r/${RUN_ID}`);
  await expect(page.getByRole("heading", { name: "Outputs" })).toBeVisible();
  await expect(promote).toHaveCount(0);
});

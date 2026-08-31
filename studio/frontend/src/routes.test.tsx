import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Which URL reaches which screen, and nothing else.
 *
 * Every page is stubbed. What `routes.tsx` decides is the mapping — a page's own
 * behaviour is its own file's problem, and rendering the real ones here would
 * pull in the auth stack, the library context and a request per screen to assert
 * something none of them influence.
 *
 * **It matters more than it looks.** The route table is the one place the entity
 * ids in the URL are turned into a screen, and a wrong turn there is invisible
 * until somebody opens a link: a bad listing is a blank page, a bad route is the
 * *wrong* page, rendered confidently. It also pins the three shapes that are
 * easy to lose — `/f` with no id, which is the library root; `/p/<id>/r/<id>`,
 * which must not be swallowed by the project route above it; and
 * `/auth/callback`, which must not be swallowed by the catch-all below it.
 */
// The layout is stubbed for the same reason every page is: it renders the
// header, the header asks `useAuth`, and this file's whole point is to exercise
// the route table without the auth stack. What it must keep is the `Outlet` —
// the pages below it render *through* the layout now, so a stub without one
// would make every assertion here fail for a reason that has nothing to do with
// routing.
vi.mock("./components/layout/AppLayout", () => ({ AppLayout: () => <Outlet /> }));

vi.mock("./pages/HomePage", () => ({ HomePage: () => <div>home</div> }));
vi.mock("./pages/CharactersPage", () => ({ CharactersPage: () => <div>characters</div> }));
vi.mock("./pages/ProjectsPage", () => ({ ProjectsPage: () => <div>projects</div> }));
vi.mock("./pages/CharacterPage", () => ({ CharacterPage: () => <div>character</div> }));
vi.mock("./pages/ProjectPage", () => ({ ProjectPage: () => <div>project</div> }));
vi.mock("./pages/RunPage", () => ({ RunPage: () => <div>run</div> }));
vi.mock("./pages/ScenePage", () => ({ ScenePage: () => <div>scene</div> }));
vi.mock("./pages/MoviePage", () => ({ MoviePage: () => <div>movie</div> }));
vi.mock("./pages/BrowsePage", () => ({ BrowsePage: () => <div>browser</div> }));
vi.mock("./pages/ObjectPage", () => ({ ObjectPage: () => <div>object</div> }));
vi.mock("./pages/AuthCallbackPage", () => ({ AuthCallbackPage: () => <div>callback</div> }));

import { StudioRoutes } from "./routes";
import { TestProviders } from "./test-providers";

// Testing Library registers its cleanup with Vitest globals on; they are off
// here, so an unmounted tree would stay in the document.
afterEach(cleanup);

function at(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <StudioRoutes />
    </MemoryRouter>,
  { wrapper: TestProviders },
  );
}

describe("the route table", () => {
  it.each([
    ["/", "home"],
    ["/characters", "characters"],
    ["/projects", "projects"],
    ["/c/char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15", "character"],
    ["/p/proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9", "project"],
    [
      "/p/proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9/r/run-77c2f0a8-31b5-4e62-9a07-c4d8e15b3f60",
      "run",
    ],
    ["/s/scene-0001", "scene"],
    ["/m/movie-0001", "movie"],
    ["/f", "browser"],
    ["/f/node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61", "browser"],
    // The object screen is its own page. This used to reach the browser, which
    // is exactly the coupling the rework removed: opening a file meant
    // rendering the folder tree with the file laid over it.
    ["/o/node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5", "object"],
    // No id, which is "play this feed from the start" — see `feedPath`.
    ["/o", "object"],
    // Above the catch-all, or Cognito's `?code=` is redirected away and the
    // hosted page loops.
    ["/auth/callback", "callback"],
  ])("sends %s to the %s screen", (path, screenName) => {
    at(path);
    expect(screen.getByText(screenName)).toBeDefined();
  });

  it("does not let the catch-all swallow the Cognito callback", () => {
    // The path arrives carrying `?code=` and `?state=`, and the catch-all one
    // line below it would `Navigate` home — discarding the code and looping
    // straight back to the hosted sign-in page. Ordering is the whole fix, and
    // nothing but this assertion pins it.
    at("/auth/callback?code=abc123&state=xyz789");
    expect(screen.getByText("callback")).toBeDefined();
  });

  it("sends an old key-shaped share link home rather than resolving it", () => {
    // Studio used to hand out the S3 key as the URL and match those by
    // exclusion, which is what kept every top-level segment but `/f/` and `/o/`
    // unusable. The bridge is gone with this rework — no back-compat is carried —
    // and removing it is what made `/c/`, `/p/`, `/s/` and `/m/` available.
    at("/projects/a-project/runs/2026-08-19_09-40-12_nano/output/clip.mp4");
    expect(screen.getByText("home")).toBeDefined();
  });
});

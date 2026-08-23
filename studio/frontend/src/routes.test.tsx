import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
 * *wrong* page, rendered confidently. It also pins the two shapes that are easy
 * to lose — `/f` with no id, which is the library root, and `/p/<id>/r/<id>`,
 * which must not be swallowed by the project route above it.
 */
vi.mock("./pages/HomePage", () => ({ HomePage: () => <div>home</div> }));
vi.mock("./pages/CharacterPage", () => ({ CharacterPage: () => <div>character</div> }));
vi.mock("./pages/ProjectPage", () => ({ ProjectPage: () => <div>project</div> }));
vi.mock("./pages/RunPage", () => ({ RunPage: () => <div>run</div> }));
vi.mock("./pages/ScenePage", () => ({ ScenePage: () => <div>scene</div> }));
vi.mock("./pages/MoviePage", () => ({ MoviePage: () => <div>movie</div> }));
vi.mock("./pages/BrowsePage", () => ({ BrowsePage: () => <div>browser</div> }));

import { StudioRoutes } from "./routes";

// Testing Library registers its cleanup with Vitest globals on; they are off
// here, so an unmounted tree would stay in the document.
afterEach(cleanup);

function at(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <StudioRoutes />
    </MemoryRouter>,
  );
}

describe("the route table", () => {
  it.each([
    ["/", "home"],
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
    ["/o/node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5", "browser"],
  ])("sends %s to the %s screen", (path, screenName) => {
    at(path);
    expect(screen.getByText(screenName)).toBeDefined();
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

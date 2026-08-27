import { Navigate, Route, Routes } from "react-router-dom";

import { CALLBACK_PATH } from "./auth/oauth";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { BrowsePage } from "./pages/BrowsePage";
import { CharacterPage } from "./pages/CharacterPage";
import { HomePage } from "./pages/HomePage";
import { MoviePage } from "./pages/MoviePage";
import { ProjectPage } from "./pages/ProjectPage";
import { RunPage } from "./pages/RunPage";
import { ScenePage } from "./pages/ScenePage";

/**
 * Nine routes. Eight name an id; the ninth is where Cognito lands.
 *
 * That is the property the whole entity model exists to give the URL: a
 * character, a project, a run, a scene, a movie and a node are all addressed by
 * a UUID that never changes, so a link keeps working through every rename and
 * every move. Slugs appear on the page and never in the path.
 *
 * ```
 * /                       home — characters, projects, and the recent reel
 * /c/<char_id>            character: profile, references, its folders, files
 * /p/<proj_id>            project: overview, runs, scenes, movies, inputs, files
 * /p/<proj_id>/r/<run_id> one run — its envelope, outputs, chain and payloads
 * /s/<scene_id>           scene
 * /m/<movie_id>           movie
 * /f          /f/<id>     the folder browser: the library root, or one folder
 * /o/<id>                 one file, open
 * /auth/callback          where Cognito Managed Login returns with ?code=
 * ```
 *
 * **There is no legacy redirect any more.** Studio used to hand out the S3 key
 * as the URL and match those paths by *exclusion*, which is what reserved `/f/`
 * and `/o/` and what kept every other top-level segment unusable. That bridge is
 * removed with this rework rather than carried: no back-compat is required, and
 * removing it is what makes `/c/`, `/p/`, `/s/` and `/m/` available. An
 * unrecognised path therefore goes to home instead of to a resolver.
 *
 * `/f` and `/f/:nodeId` are one screen. The library root has no id a URL could
 * carry before the first request answers — see `utils/location` — so the browser
 * addresses it by the absence of one.
 *
 * Separate from `App` so the table can be exercised without the auth stack: the
 * gate renders a "not configured" notice when no user pool is set, which in a
 * test is every route resolving to the same thing. What the tests here assert is
 * which component a URL reaches, and that is this file and nothing else.
 *
 * Three things outside it have to agree. CloudFront's viewer-request function
 * must send all of these to `index.html`, which it does by routing on location
 * rather than on extension (`infra/modules/hosting`). Sign-out sends the user
 * to `/`. And `/auth/callback` is registered character for character in the
 * user pool client's `callback_urls` (`infra/modules/auth`) — which is why the
 * path is the `CALLBACK_PATH` constant the authorize URL is built from rather
 * than a literal written twice.
 */
export function StudioRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />

      <Route path="/c/:characterId" element={<CharacterPage />} />
      <Route path="/p/:projectId" element={<ProjectPage />} />
      <Route path="/p/:projectId/r/:runId" element={<RunPage />} />
      <Route path="/s/:sceneId" element={<ScenePage />} />
      <Route path="/m/:movieId" element={<MoviePage />} />

      <Route path="/f" element={<BrowsePage />} />
      <Route path="/f/:nodeId" element={<BrowsePage />} />
      <Route path="/o/:nodeId" element={<BrowsePage />} />

      {/* **Above the catch-all, and it has to be.** Cognito returns to this
          path with `?code=`; matched by `*` below it would redirect home,
          discarding the code and looping straight back to the hosted page. */}
      <Route path={CALLBACK_PATH} element={<AuthCallbackPage />} />

      {/* `replace`, not a render of home at the wrong address: a bookmark that
          has stopped meaning anything should leave the address bar honest, and
          pushing would put the dead URL one back-press away. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

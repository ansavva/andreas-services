// There is no auth SDK to configure here any more. `auth/oauth.ts` reads its
// two build-time values at import time and holds the session in
// `localStorage`, so nothing has to run before the first render.
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

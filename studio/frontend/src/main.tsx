// `./amplify` must be imported before anything that reaches for
// `aws-amplify/auth`, so `Amplify.configure` has already run by the time the
// auth context's first session lookup fires.
import "./amplify";
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

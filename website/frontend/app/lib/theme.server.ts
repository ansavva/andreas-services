/**
 * Cookie-backed light/dark theme. Stored server-side so SSR renders the correct
 * `data-theme` with no flash of the wrong theme, and it works without JS.
 */
import { createCookie } from "react-router";

export type Theme = "light" | "dark";

const cookie = createCookie("theme", {
  path: "/",
  sameSite: "lax",
  maxAge: 60 * 60 * 24 * 365, // 1 year
});

export async function getTheme(request: Request): Promise<Theme> {
  const value = await cookie.parse(request.headers.get("Cookie"));
  return value === "dark" ? "dark" : "light";
}

export async function serializeTheme(theme: Theme): Promise<string> {
  return cookie.serialize(theme);
}

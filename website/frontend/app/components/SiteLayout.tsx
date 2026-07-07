import type { ReactNode } from "react";

import { Footer } from "./Footer";
import { Nav } from "./Nav";

/** Shared chrome (nav + footer) for the public marketing pages. */
export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <Nav />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

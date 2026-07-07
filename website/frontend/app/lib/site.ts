/** Static site metadata shared across pages (nav, footer, socials, positioning). */

export const SITE = {
  name: "Andreas Services",
  tagline: "AI automation that actually works.",
  credibility: "12+ years engineering · former Senior Development Manager · builds with AI in public",
} as const;

export const NAV_LINKS = [
  { to: "/services", label: "Work with me" },
  { to: "/writing", label: "Writing" },
  { to: "/about", label: "About" },
] as const;

export const SOCIALS = [
  { label: "YouTube", href: "https://www.youtube.com/@SavvaAndreas" },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/andreas-savva-dev" },
  { label: "TikTok", href: "https://www.tiktok.com/@andreassavvanyc" },
  { label: "Instagram", href: "https://www.instagram.com/andreassavvanyc" },
] as const;

/** Public Cal.com handle for the "book an intro call" embed/link. */
export const CAL_LINK = import.meta.env.VITE_CAL_LINK ?? "andreas/intro";

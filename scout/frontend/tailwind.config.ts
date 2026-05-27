import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--color-background)",
        surface: "var(--color-surface)",
        "surface-hover": "var(--color-surface-hover)",
        border: "var(--color-border)",
        rule: "var(--color-rule)",
        primary: "var(--color-primary)",
        "primary-hover": "var(--color-primary-hover)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-muted": "var(--color-text-muted)",
        badge: "var(--color-badge)",
        "badge-text": "var(--color-badge-text)",
      },
      fontFamily: {
        serif: ["Fraunces", "Georgia", "Times New Roman", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
      },
      fontSize: {
        display: ["clamp(2.5rem, 8vw, 5.5rem)", { lineHeight: "0.95", letterSpacing: "-0.02em" }],
        hero: ["clamp(2rem, 5.5vw, 3.5rem)", { lineHeight: "1.02", letterSpacing: "-0.015em" }],
      },
      letterSpacing: {
        eyebrow: "0.22em",
      },
    },
  },
  plugins: [],
};

export default config;

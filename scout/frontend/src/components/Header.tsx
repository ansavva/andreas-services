import { Link } from "react-router-dom";

export function Header() {
  return (
    <header className="border-b border-[var(--color-rule)] bg-[var(--color-surface)]">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-5 sm:px-6">
        <Link to="/" className="group no-underline">
          <span className="block font-serif text-2xl leading-none tracking-tight text-[var(--color-text-primary)] sm:text-3xl">
            Scout
          </span>
          <span className="eyebrow mt-1.5 hidden text-[var(--color-text-muted)] sm:block">
            A curated edit
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/admin"
            className="eyebrow text-[var(--color-text-secondary)] no-underline hover:text-[var(--color-text-primary)] hover:underline"
          >
            Admin
          </Link>
        </nav>
      </div>
    </header>
  );
}

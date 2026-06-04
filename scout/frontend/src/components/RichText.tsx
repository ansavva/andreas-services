import { Fragment, type ReactNode } from "react";

// One token: a markdown link `[label](url)` or a bare http(s) URL. The
// alternation tries the markdown form first so a URL already wrapped in a
// markdown link isn't also matched as a bare URL.
const TOKEN = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<>"]+)/g;

// Trailing punctuation that almost always belongs to the surrounding prose
// rather than the URL itself (e.g. "see https://x.org." or "(https://x.org)").
const TRAILING = /[.,;:!?)\]]+$/;

/**
 * Turn the source-captured text into React nodes, rendering markdown links and
 * bare URLs as real, clickable anchors. Everything else is preserved verbatim
 * so the caller's `whitespace-pre-line` keeps the original line breaks.
 *
 * Links open in a new tab and use `break-words` so a long URL wraps inside its
 * column instead of overflowing the layout.
 */
export function linkify(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  TOKEN.lastIndex = 0;

  while ((match = TOKEN.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));

    const [, mdLabel, mdUrl, bareUrl] = match;
    let label: string;
    let url: string;
    let trailing = "";

    if (mdUrl) {
      label = mdLabel;
      url = mdUrl;
    } else {
      url = bareUrl;
      const trimmed = url.replace(TRAILING, "");
      trailing = url.slice(trimmed.length);
      url = trimmed;
      label = url;
    }

    nodes.push(
      <a
        key={match.index}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="break-words text-[var(--color-text-primary)] underline underline-offset-2 hover:opacity-70"
      >
        {label}
      </a>
    );
    if (trailing) nodes.push(trailing);

    last = match.index + match[0].length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes.map((n, i) => <Fragment key={i}>{n}</Fragment>);
}

/**
 * Renders source-captured prose with clickable, wrapping links. Pass the same
 * classes the surrounding copy uses; `break-words` is added so long URLs wrap.
 */
export function RichText({ text, className }: { text: string; className?: string }) {
  return <div className={`break-words ${className ?? ""}`}>{linkify(text)}</div>;
}

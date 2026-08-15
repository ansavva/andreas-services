import { useMemo } from "react";

/**
 * Just enough markdown for the subject `profile.md` files.
 *
 * Deliberately not a markdown library. These files are headings, paragraphs,
 * lists and the occasional bold run, and pulling in a parser plus a sanitiser
 * to render them would be more dependency than the feature is worth. Everything
 * is built as React elements from plain text — no `dangerouslySetInnerHTML`
 * anywhere — so bucket contents can never inject markup into the app.
 */
export function MarkdownView({ source }: { source: string }) {
  const blocks = useMemo(() => parseBlocks(source), [source]);

  return (
    <div className="flex flex-col gap-3 p-4">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const sizes = ["text-2xl", "text-xl", "text-lg", "text-base", "text-sm", "text-sm"];
          return (
            <p
              key={index}
              className={`font-heading font-semibold text-ink ${sizes[block.level - 1] ?? "text-base"} ${
                index === 0 ? "" : "mt-3"
              }`}
            >
              {inline(block.text)}
            </p>
          );
        }

        if (block.type === "list") {
          return (
            <ul key={index} className="list-disc pl-6 font-body text-sm text-muted">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="mb-1">
                  {inline(item)}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p key={index} className="whitespace-pre-wrap font-body text-sm leading-relaxed text-muted">
            {inline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] };

function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flush = () => {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", text: paragraph.join("\n") });
      paragraph = [];
    }
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  };

  for (const line of source.split("\n")) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);

    if (heading) {
      flush();
      blocks.push({ type: "heading", level: heading[1]!.length, text: heading[2]! });
    } else if (bullet) {
      if (paragraph.length) {
        blocks.push({ type: "paragraph", text: paragraph.join("\n") });
        paragraph = [];
      }
      list.push(bullet[1]!);
    } else if (line.trim() === "") {
      flush();
    } else {
      if (list.length) {
        blocks.push({ type: "list", items: list });
        list = [];
      }
      paragraph.push(line);
    }
  }

  flush();
  return blocks;
}

/** `**bold**`, `*italic*` and `` `code` `` — as elements, never as HTML. */
function inline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));

    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      parts.push(
        <code key={match.index} className="rounded-sm bg-surface-alt px-1 font-mono text-xs text-ink">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      parts.push(<em key={match.index}>{token.slice(1, -1)}</em>);
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

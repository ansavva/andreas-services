import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createLineBreakNode,
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $isParagraphNode,
  $getSelection,
  $isRangeSelection,
  KEY_DOWN_COMMAND,
  COMMAND_PRIORITY_CRITICAL,
} from "lexical";

import { $createTokenNode, TokenNode } from "./TokenNode";

/** One thing a `+` can insert, and what kind of pill it becomes. */
export interface PromptToken {
  name: string;
  kind: "block" | "computed";
  /** First line of the block, or what the computed value is filled from. */
  hint?: string;
}

const PLACEHOLDER = /\{[a-z_][a-z0-9_]*\}/g;

/**
 * A prompt template, with its `{placeholders}` drawn as pills.
 *
 * ## Why this exists
 *
 * A template is text with named holes, and it was typed into a plain box: a
 * mistyped `{face_onl}` looked exactly like a correct one and did not fail until
 * the angle was drafted and refused. A pill cannot be mistyped, because it is
 * inserted rather than written.
 *
 * ## The invariant everything here protects
 *
 * **The value is a plain string and the round trip is byte-exact.** Assembly is
 * `string.Formatter().vformat` over `{name}`, and `plan_digest` hashes the
 * prompt into the approval — so an editor that normalised one space or dropped
 * one trailing newline would silently stale every approval already given, for a
 * change nobody made.
 *
 * That invariant is held by construction rather than by care: a pill is a
 * `TextNode` whose text IS `{name}`, so `root.getTextContent()` is the string.
 * There is no serialiser to keep in step, which is the only reason this is a
 * safe thing to put in front of a hashed payload.
 *
 * ## Reusable on purpose
 *
 * It takes its tokens as a prop and knows nothing about reference angles, so a
 * run's prompt editor can hand it a different list.
 */
export function TokenizedPromptEditor({
  value,
  onValueChange,
  tokens,
  ariaLabel,
}: {
  value: string;
  onValueChange: (next: string) => void;
  tokens: PromptToken[];
  ariaLabel?: string;
}) {
  const kinds = useMemo(
    () => Object.fromEntries(tokens.map((t) => [t.name, t.kind])) as Record<string, "block" | "computed">,
    [tokens],
  );

  return (
    <LexicalComposer
      initialConfig={{
        namespace: "prompt",
        nodes: [TokenNode],
        // Thrown, not swallowed. An editor that silently drops a node it cannot
        // read would hand back a prompt missing part of itself, and the digest
        // would move without anybody editing anything.
        onError: (error: Error) => {
          throw error;
        },
        theme: {},
      }}
    >
      <div className="rounded border border-line p-2">
        <PlainTextPlugin
          contentEditable={
            <ContentEditable
              aria-label={ariaLabel ?? "Prompt"}
              // `whitespace-pre-wrap`: blank lines are part of the prompt now —
              // they survive assembly and reach the model — so the editor has to
              // show them rather than collapse them like ordinary HTML.
              className="min-h-24 whitespace-pre-wrap font-mono text-sm outline-none"
            />
          }
          placeholder={<span className="text-muted">Write the angle's prompt…</span>}
          ErrorBoundary={LexicalErrorBoundary}
        />
        <Hydrate value={value} kinds={kinds} />
        <OnChangePlugin
          ignoreSelectionChange
          onChange={(state) => state.read(() => onValueChange($getRoot().getTextContent()))}
        />
        <TypeaheadPlugin tokens={tokens} kinds={kinds} />
      </div>
    </LexicalComposer>
  );
}

/**
 * Put the string into the editor, once, as text and pills.
 *
 * Only when the incoming value is not what the editor already holds — otherwise
 * every keystroke would rebuild the document and put the caret back at the top.
 */
function Hydrate({ value, kinds }: { value: string; kinds: Record<string, "block" | "computed"> }) {
  const [editor] = useLexicalComposerContext();
  const held = useRef<string | null>(null);

  useEffect(() => {
    if (held.current === value) return;
    held.current = value;
    editor.update(() => {
      const root = $getRoot();
      root.clear();
      const paragraph = $createParagraphNode();
      // Line breaks are their own node in Lexical, and `getTextContent()` gives
      // each of them back as "\n" — which is what makes the round trip exact
      // for a paragraphed prompt.
      value.split("\n").forEach((line, index) => {
        if (index > 0) paragraph.append($createLineBreakNode());
        let at = 0;
        for (const found of line.matchAll(PLACEHOLDER)) {
          const name = found[0].slice(1, -1);
          if (found.index > at) paragraph.append($createTextNode(line.slice(at, found.index)));
          paragraph.append($createTokenNode(found[0], kinds[name] ?? "computed"));
          at = found.index + found[0].length;
        }
        if (at < line.length) paragraph.append($createTextNode(line.slice(at)));
      });
      root.append(paragraph);
    });
  }, [editor, kinds, value]);

  return null;
}

/**
 * `+` opens the list; a click or Enter inserts the pill.
 *
 * Deliberately not Lexical's own typeahead plugin. That one owns the caret, the
 * menu and the match, which is more machinery than one trigger character needs —
 * and its match logic is written for `@mentions`, where the query is part of the
 * document. Here the `+` is thrown away.
 */
function TypeaheadPlugin({
  tokens,
  kinds,
}: {
  tokens: PromptToken[];
  kinds: Record<string, "block" | "computed">;
}) {
  const [editor] = useLexicalComposerContext();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const matches = useMemo(
    () =>
      tokens.filter((t) => t.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8),
    [query, tokens],
  );

  const insert = useCallback(
    (name: string) => {
      editor.update(() => {
        const pill = $createTokenNode(`{${name}}`, kinds[name] ?? "computed");
        const selection = $getSelection();
        if ($isRangeSelection(selection)) {
          selection.insertNodes([pill]);
          return;
        }
        // No caret — the list was opened from a click rather than from typing.
        // Appending is the honest answer: refusing would make the button do
        // nothing at all, which reads as broken rather than as "focus first".
        const last = $getRoot().getLastChild();
        if ($isParagraphNode(last)) last.append(pill);
      });
      setOpen(false);
      setQuery("");
    },
    [editor, kinds],
  );

  useEffect(
    () =>
      editor.registerCommand(
        KEY_DOWN_COMMAND,
        (event: KeyboardEvent) => {
          if (event.key === "+" && !open) {
            event.preventDefault();
            setOpen(true);
            setQuery("");
            return true;
          }
          if (!open) return false;
          if (event.key === "+") {
            // The escape hatch. Stealing a printable character means a prompt
            // that genuinely wants one has no way to say it, so a second `+`
            // closes the list and types the character it was standing for.
            event.preventDefault();
            setOpen(false);
            setQuery("");
            editor.update(() => {
              const selection = $getSelection();
              if ($isRangeSelection(selection)) selection.insertText("+");
            });
            return true;
          }
          if (event.key === "Escape") {
            setOpen(false);
            return true;
          }
          if (event.key === "Enter" && matches[0]) {
            event.preventDefault();
            insert(matches[0].name);
            return true;
          }
          if (event.key === "Backspace") {
            setQuery((q) => q.slice(0, -1));
            return true;
          }
          if (event.key.length === 1) {
            event.preventDefault();
            setQuery((q) => q + event.key);
            return true;
          }
          return false;
        },
        // CRITICAL, not LOW: Lexical's own text insertion runs first at any
        // lower priority, so the trigger arrived as a literal `+` in the
        // document and the list never opened.
        COMMAND_PRIORITY_CRITICAL,
      ),
    [editor, insert, matches, open],
  );

  if (!open) return null;

  return (
    <div role="listbox" aria-label="Insert a placeholder" className="mt-1 flex flex-col gap-1">
      <span className="font-mono text-xs text-muted">+{query}</span>
      {matches.map((token) => (
        <button
          key={token.name}
          type="button"
          role="option"
          aria-selected={false}
          onClick={() => insert(token.name)}
          className="flex items-baseline gap-2 rounded px-2 py-1 text-left hover:bg-surface-alt"
        >
          <span className="font-mono text-sm">{`{${token.name}}`}</span>
          <span className="truncate text-xs text-muted">
            {token.kind === "computed" ? "filled from the character" : token.hint}
          </span>
        </button>
      ))}
      {matches.length === 0 ? (
        <span className="px-2 py-1 text-xs text-muted">Nothing matches “{query}”.</span>
      ) : null}
    </div>
  );
}

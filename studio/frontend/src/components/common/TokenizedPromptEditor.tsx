import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { createPortal } from "react-dom";

import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  LexicalTypeaheadMenuPlugin,
  MenuOption,
} from "@lexical/react/LexicalTypeaheadMenuPlugin";
import type { MenuTextMatch } from "@lexical/react/LexicalTypeaheadMenuPlugin";
import {
  $createLineBreakNode,
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  COMMAND_PRIORITY_HIGH,
  KEY_ENTER_COMMAND,
  TextNode,
} from "lexical";

import { $createTokenNode, TokenNode } from "./TokenNode";

/** One thing the menu can insert, and what kind of pill it becomes. */
export interface PromptToken {
  name: string;
  kind: "block" | "computed";
  /** First line of the block, or what the computed value is filled from. */
  hint?: string;
  /**
   * Drawn as a pill, but never offered by the menu.
   *
   * The bare spelling — `{scale_face}` rather than `{block.scale_face}` — still
   * resolves and still has to LOOK like what it is, or every template written
   * before the namespaces reads as broken. It is not offered, because there is
   * no reason to write a new one.
   */
  legacy?: boolean;
}

//: A placeholder name: `block.scale_face`, `slot.identity`, or a positional
//: `character.1.build.face`.
//:
//: **Every segment after the first may be digits**, and requiring a leading
//: letter on all of them is what stopped `{character.1.top}` from ever drawing
//: as a pill. It looked like a rendering bug and read like a broken citation
//: sitting between block pills that worked — a prompt written entirely in the
//: one spelling the fill accepts showed none of it as recognised. The first
//: segment is still a namespace, so it keeps its letter.
const PLACEHOLDER = /\{[a-z_][a-z0-9_]*(?:\.[a-z0-9_]+)*\}/g;

/**
 * `{` plus the name being typed, immediately before the caret.
 *
 * **The trigger is `{` because that is the character a placeholder starts
 * with.** It was `+`, which is a key nobody can guess and nothing on the page
 * announced — so the only way to insert a pill was to be told. Triggering on the
 * brace means the menu appears while you type the thing you were going to type
 * anyway, and there is nothing left to teach.
 *
 * The leading group refuses a doubled brace, because `{{` is how a template says
 * a LITERAL brace and offering a placeholder there would be offering the one
 * thing that cannot go there.
 */
const TRIGGER = /(^|[^{])(\{([a-z0-9_.]*))$/;

/**
 * What the menu would open on, given the text before the caret.
 *
 * Exported because it is the whole specification of when the menu appears, and
 * it is the one part of the typeahead a jsdom test can reach: opening the real
 * menu needs a live caret, which nothing in jsdom provides.
 */
export function promptTriggerMatch(text: string) {
  const found = TRIGGER.exec(text);
  if (found === null) return null;
  return {
    leadOffset: found.index + (found[1] ?? "").length,
    matchingString: found[3] ?? "",
    replaceableString: found[2] ?? "",
  };
}

/**
 * The next `{placeholder}` in `text` at or after `from`.
 *
 * A doubled brace is skipped: `{{` and `}}` are how a template says a LITERAL
 * brace — `assemble` says so when it refuses a malformed one — and drawing an
 * escape as a citation would claim the prompt cites something it does not.
 */
function nextPlaceholder(text: string, from = 0) {
  PLACEHOLDER.lastIndex = from;
  let found = PLACEHOLDER.exec(text);
  while (found !== null) {
    const start = found.index;
    const end = start + found[0].length;
    if (text[start - 1] !== "{" && text[end] !== "}") {
      return { token: found[0], name: found[0].slice(1, -1), start, end };
    }
    found = PLACEHOLDER.exec(text);
  }
  return null;
}

/**
 * A prompt template, with its `{placeholders}` drawn as pills.
 *
 * ## Why this exists
 *
 * A template is text with named holes, and it was typed into a plain box: a
 * mistyped `{face_onl}` looked exactly like a correct one and did not fail until
 * the angle was drafted and refused. A pill cannot be mistyped, because it
 * either names a real placeholder or it does not become one.
 *
 * ## The invariant everything here protects
 *
 * **The value is a plain string and the round trip is byte-exact.** Assembly is
 * `string.Formatter().vformat` over `{name}`, and the fingerprint hashes the
 * prompt — so an editor that normalised one space or dropped one trailing
 * newline would silently move every fingerprint, for a change nobody made.
 *
 * That invariant is held by construction rather than by care: a pill is a
 * `TextNode` whose text IS `{name}`, so `root.getTextContent()` is the string.
 * There is no serialiser to keep in step, which is the only reason this is a
 * safe thing to put in front of a hashed payload.
 *
 * ## Two ways in, and neither has to be taught
 *
 * Type the placeholder — `Pillify` turns it into a pill on the closing brace —
 * or take it from the menu that opens on `{`. The menu is the shortcut, not the
 * entrance, which is what the hand-rolled version got wrong: it was the only way
 * in, and it was a key combination with nothing on screen to name it.
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
  placeholder = "Write the angle's prompt… type { for a placeholder.",
  className = "rounded-none border border-line p-2",
  contentClassName = "min-h-24",
  onSubmit,
  focusKey,
}: {
  value: string;
  onValueChange: (next: string) => void;
  tokens: PromptToken[];
  ariaLabel?: string;
  placeholder?: string;
  /** The box around the editor. The create bar hands it no border of its own. */
  className?: string;
  /** Sizing for the editable itself: a min height, a max height and a scroll. */
  contentClassName?: string;
  /**
   * Enter sends, Shift+Enter breaks the line.
   *
   * Only when given: the template editor keeps Enter as a newline, because a
   * template is paragraphs. The create bar is a chat box and Enter is what a
   * chat box means by it. The `{` menu still takes Enter first while it is
   * open — choosing a pill must not send the prompt half-written.
   */
  onSubmit?: () => void;
  /** Focus the editor whenever this changes. What "load a run into the bar" does. */
  focusKey?: number;
}) {
  const kinds = useMemo(
    () => Object.fromEntries(tokens.map((t) => [t.name, t.kind])) as Record<string, "block" | "computed">,
    [tokens],
  );

  /**
   * Whether the `{` menu is open — read by the Enter handler, which must yield
   * to it. A ref rather than state: the handler is a Lexical command listener
   * and the menu toggles many times a second while a name is typed.
   */
  const menuOpen = useRef(false);

  // **The string the editor and the caller last agreed on.**
  //
  // Shared by both directions on purpose. It lived inside `Hydrate` and was
  // written only when a NEW value arrived from outside, so a value that came
  // back from the editor's own keystroke never matched it: every character
  // typed rebuilt the whole document and put the caret back at the top, which
  // made the box unusable for anything longer than one word.
  //
  // Written here whenever the editor emits, it says "this text is already in
  // the editor" — so an echo of your own typing hydrates nothing, and a value
  // genuinely changed by the caller (Revert, a fetch landing) still does.
  const held = useRef<string | null>(null);

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
      <div className={className}>
        {/* `relative` on a box with no padding of its own, so the placeholder
            can sit exactly where the first character will land. */}
        <div className="relative">
        <PlainTextPlugin
          contentEditable={
            <ContentEditable
              aria-label={ariaLabel ?? "Prompt"}
              // `whitespace-pre-wrap`: blank lines are part of the prompt now —
              // they survive assembly and reach the model — so the editor has to
              // show them rather than collapse them like ordinary HTML.
              className={`${contentClassName} whitespace-pre-wrap font-mono text-sm leading-6 outline-none`}
            />
          }
          placeholder={
            <span className="pointer-events-none absolute left-0 top-0 truncate font-mono text-sm leading-6 text-muted">
              {placeholder}
            </span>
          }
          ErrorBoundary={LexicalErrorBoundary}
        />
        </div>
        {/* Cmd-Z. Lexical ships no history unless it is asked for, so undo did
            nothing at all — in a box whose whole purpose is trying wordings out. */}
        <HistoryPlugin />
        <Hydrate value={value} held={held} />
        <Pillify kinds={kinds} />
        {onSubmit && <SubmitOnEnter onSubmit={onSubmit} menuOpen={menuOpen} />}
        <Focus focusKey={focusKey} />
        <OnChangePlugin
          ignoreSelectionChange
          onChange={(state) =>
            state.read(() => {
              const next = $getRoot().getTextContent();
              if (next === held.current) return;
              held.current = next;
              onValueChange(next);
            })
          }
        />
        <Typeahead tokens={tokens} kinds={kinds} menuOpen={menuOpen} />
      </div>
    </LexicalComposer>
  );
}

/**
 * Enter sends; Shift+Enter is still a line break.
 *
 * Registered at `COMMAND_PRIORITY_HIGH`, above the `{` menu's own Enter and
 * above the plain-text plugin's, so it is asked first — and it declines when
 * the menu is open, so the keystroke falls through to the menu and picks the
 * highlighted pill instead of sending a half-written citation. It declines on
 * Shift too, which leaves the newline to the plugin that always drew one.
 */
function SubmitOnEnter({
  onSubmit,
  menuOpen,
}: {
  onSubmit: () => void;
  menuOpen: MutableRefObject<boolean>;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(
    () =>
      editor.registerCommand<KeyboardEvent | null>(
        KEY_ENTER_COMMAND,
        (event) => {
          if (event === null || event.shiftKey || event.isComposing || menuOpen.current) return false;
          event.preventDefault();
          onSubmit();
          return true;
        },
        COMMAND_PRIORITY_HIGH,
      ),
    [editor, menuOpen, onSubmit],
  );

  return null;
}

/** Focus the editor when asked to — loading a run into the bar asks. */
function Focus({ focusKey }: { focusKey: number | undefined }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (focusKey === undefined || focusKey === 0) return;
    editor.focus();
  }, [editor, focusKey]);

  return null;
}

/**
 * Put the string into the editor, once, as text and pills.
 *
 * Only when the incoming value is not what the editor already holds — otherwise
 * every keystroke would rebuild the document and put the caret back at the top.
 */
function Hydrate({
  value,
  held,
}: {
  value: string;
  held: MutableRefObject<string | null>;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (held.current === value) return;
    // Deliberately NOT recorded here. The rebuild makes the editor emit, and
    // that emission is what records it — which is also what lets the caller
    // hear the parsed value once on mount.
    editor.update(() => {
      const root = $getRoot();
      root.clear();
      const paragraph = $createParagraphNode();
      // Line breaks are their own node in Lexical, and `getTextContent()` gives
      // each of them back as "\n" — which is what makes the round trip exact
      // for a paragraphed prompt.
      // **Plain text, and the transform makes the pills.** It used to build
      // them here too, which meant two implementations of "this run of
      // characters is a placeholder" — and the one a person's typing went
      // through was the one with no test on it.
      value.split("\n").forEach((line, index) => {
        if (index > 0) paragraph.append($createLineBreakNode());
        if (line !== "") paragraph.append($createTextNode(line));
      });
      root.append(paragraph);
    });
  }, [editor, held, value]);

  return null;
}

/**
 * A `{placeholder}` becomes a pill — whether typed, pasted or loaded.
 *
 * **The only place text becomes a pill.** `Hydrate` puts the stored string in as
 * plain text and this turns it into pills, so a prompt read from the API and a
 * prompt typed by hand go through exactly the same code.
 *
 * **This is what makes the menu optional rather than mandatory.** Lexical's own
 * `registerLexicalTextEntity` is the shape of this and is deliberately not used:
 * its transform converts a target node back to plain text whenever the node
 * beside it is a text entity or its mode is not normal, which would un-pill both
 * of two ADJACENT placeholders — `{scale_face}{face_only}` is a real template —
 * and would un-pill anything the moment you typed a character after it, because
 * these nodes are in `token` mode. No reverse transform is needed here for the
 * same reason: token mode means the caret cannot get inside a pill, so a pill's
 * text cannot stop matching.
 */
function Pillify({ kinds }: { kinds: Record<string, "block" | "computed"> }) {
  const [editor] = useLexicalComposerContext();

  // **A layout effect, so this is registered before `Hydrate` runs.** Passive
  // effects fire in tree order, so a plugin's position in the JSX decided
  // whether the loaded prompt got pills at all — it silently did not. Layout
  // effects all run before passive ones, which makes the ordering a phase
  // rather than a line number somebody can move.
  useLayoutEffect(
    () =>
      editor.registerNodeTransform(TextNode, (node) => {
        if (!node.isSimpleText()) return;
        const found = nextPlaceholder(node.getTextContent());
        if (found === null) return;
        // One per pass. Lexical re-runs a transform until nothing is dirty, and
        // the remainder left by the split is dirty, so a line pasted with six
        // placeholders resolves without looping here.
        const target =
          found.start === 0
            ? node.splitText(found.end)[0]
            : node.splitText(found.start, found.end)[1];
        target?.replace($createTokenNode(found.token, kinds[found.name] ?? "computed"));
      }),
    [editor, kinds],
  );

  return null;
}

class TokenOption extends MenuOption {
  token: PromptToken;

  constructor(token: PromptToken) {
    super(token.name);
    this.token = token;
  }
}

/**
 * The menu that opens on `{`.
 *
 * Lexical's own typeahead plugin, rather than the hand-rolled one this replaced.
 * Three things it does that the hand-rolled one did not, each of which was a bug
 * rather than a missing nicety:
 *
 * - **The trigger and the query stay in the document.** The old one held the
 *   query in React state and threw the `+` away, so every character typed after
 *   an accidental trigger went somewhere invisible and the sentence being typed
 *   simply did not appear. Here the text is real text the whole time; dismissing
 *   the menu leaves exactly what you typed.
 * - **Arrow keys, Tab, Enter, Escape and `aria-activedescendant`**, from the
 *   framework. The old one had no highlighted option at all and Enter took the
 *   first match blindly.
 * - **The menu is anchored at the caret** in a portal, not parked under the box.
 */
function Typeahead({
  tokens,
  kinds,
  menuOpen,
}: {
  tokens: PromptToken[];
  kinds: Record<string, "block" | "computed">;
  /** Written here, read by `SubmitOnEnter` — the one thing the two share. */
  menuOpen: MutableRefObject<boolean>;
}) {
  const [editor] = useLexicalComposerContext();
  const [query, setQuery] = useState<string | null>(null);

  // **Open means "has options to pick from"**, not "the trigger matched".
  // The plugin reports open on the brace alone, before anything narrows, and
  // an empty list is closed for Enter's purposes: the menu draws nothing, so
  // there is nothing to pick and the keystroke should send.
  const [resolved, setResolved] = useState(false);
  const onOpen = useCallback(() => setResolved(true), []);
  const onClose = useCallback(() => setResolved(false), []);

  const options = useMemo(
    () =>
      tokens
        .filter((t) => !t.legacy)
        .filter((t) => t.name.toLowerCase().includes((query ?? "").toLowerCase()))
        .slice(0, 8)
        .map((token) => new TokenOption(token)),
    [query, tokens],
  );

  useEffect(() => {
    menuOpen.current = resolved && options.length > 0;
  }, [menuOpen, options.length, resolved]);

  // `promptTriggerMatch`, not a second copy of it. There WAS a second copy, and
  // when the regex grew the group that refuses `{{`, that copy went on reading
  // group 1 — which had become the character BEFORE the brace. At the start of a
  // node the query was therefore always empty and the menu never narrowed; in
  // the middle of a paragraph it was the preceding space, which matches no
  // placeholder, so no menu opened at all.
  const trigger = useCallback(
    (text: string): MenuTextMatch | null => promptTriggerMatch(text),
    [],
  );

  const select = useCallback(
    (option: TokenOption, nodeToReplace: TextNode | null, closeMenu: () => void) => {
      editor.update(() => {
        const pill = $createTokenNode(
          `{${option.token.name}}`,
          kinds[option.token.name] ?? option.token.kind,
        );
        if (nodeToReplace) {
          nodeToReplace.replace(pill);
        } else {
          const selection = $getSelection();
          if ($isRangeSelection(selection)) selection.insertNodes([pill]);
        }
        pill.selectNext(0, 0);
        closeMenu();
      });
    },
    [editor, kinds],
  );

  return (
    <LexicalTypeaheadMenuPlugin<TokenOption>
      options={options}
      onQueryChange={setQuery}
      onSelectOption={select}
      onOpen={onOpen}
      onClose={onClose}
      triggerFn={trigger}
      // A `{` typed immediately after a pill is the commonest case there is —
      // a template is mostly citations — and the default suppresses the menu
      // when the caret sits against a text entity, which every pill is.
      ignoreEntityBoundary
      menuRenderFn={(anchorElementRef, { selectedIndex, selectOptionAndCleanUp, setHighlightedIndex }) =>
        anchorElementRef.current === null || options.length === 0
          ? null
          : createPortal(
              <ul
                role="listbox"
                aria-label="Insert a placeholder"
                className="m-0 max-h-64 w-72 list-none overflow-auto rounded-none border border-line bg-card p-1 shadow-lg"
              >
                {options.map((option, index) => (
                  <li
                    key={option.key}
                    id={`typeahead-item-${index}`}
                    role="option"
                    aria-selected={selectedIndex === index}
                    ref={option.setRefElement}
                    // Without this the editor blurs on press, the caret goes,
                    // and the menu closes before the click ever lands.
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    onClick={() => {
                      setHighlightedIndex(index);
                      selectOptionAndCleanUp(option);
                    }}
                    className={`flex cursor-pointer items-baseline gap-2 rounded-none px-2 py-1 ${
                      selectedIndex === index ? "bg-surface-alt" : ""
                    }`}
                  >
                    <span className="font-mono text-sm">{`{${option.token.name}}`}</span>
                    <span className="truncate text-xs text-muted">
                      {option.token.kind === "computed"
                        ? "filled from the character"
                        : option.token.hint}
                    </span>
                  </li>
                ))}
              </ul>,
              anchorElementRef.current,
            )
      }
    />
  );
}

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  $getNodeByKey,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $isTextNode,
  COMMAND_PRIORITY_HIGH,
  COMMAND_PRIORITY_LOW,
  KEY_ENTER_COMMAND,
  SELECTION_CHANGE_COMMAND,
  TextNode,
  $setSelection,
} from "lexical";

import { citationsIn } from "../../utils/citations";
import type { Citation } from "../../utils/citations";
import { CITE_TEXT } from "./citeStyle";
import { $createTokenNode, TokenNode } from "./TokenNode";

/** One thing the menu can insert, and what kind of pill it becomes. */
export interface PromptToken {
  name: string;
  kind: "block" | "computed";
  /** First line of the block, or what the computed value is filled from. */
  hint?: string;
}

/**
 * `@` plus the name being typed, immediately before the caret.
 *
 * **The trigger is `@` because that is the character a citation starts
 * with.** It was `+`, then `{` — the first a key nobody can guess, the second
 * the character the old spelling happened to start with, which nobody guesses
 * either. `@` is what every editor a person has used means by "name a thing
 * here", so the menu appears while you type the thing you were going to type
 * anyway, and there is nothing left to teach.
 *
 * The leading group refuses an `@` inside a word: `me@block` is an address,
 * and opening the menu on it would be offering a placeholder in the middle of
 * one. It is the same boundary `CITATION` keeps.
 */
const TRIGGER = /(^|[^A-Za-z0-9_])(@([a-z0-9_.]*))$/;

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
 * The first citation in `text` that names something the editor knows.
 *
 * **Known names only.** The old brace spelling pilled every well-formed
 * `{…}`, because the closing brace said the person had finished typing; an
 * `@` has no closing brace, so `@bl` is as well-formed as `@block.light` and
 * pilling it would swallow the caret mid-word. A name that is in the menu is
 * one somebody meant; anything else stays text, and the template page names
 * it in its warning instead.
 */
function nextKnown(text: string, known: ReadonlySet<string>): Citation | null {
  return citationsIn(text).find((each) => known.has(each.name)) ?? null;
}

/**
 * A prompt template, with its `@citations` drawn as pills.
 *
 * ## Why this exists
 *
 * A template is text with named holes, and it was typed into a plain box: a
 * mistyped `@block.face_onl` looked exactly like a correct one and did not
 * fail until the run was drafted and refused. A pill cannot be mistyped,
 * because it either names a real placeholder or it does not become one.
 *
 * ## The invariant everything here protects
 *
 * **The value is a plain string and the round trip is byte-exact.** The API
 * fills by scanning for `@name`, and the fingerprint hashes the prompt — so an
 * editor that normalised one space or dropped one trailing newline would
 * silently move every fingerprint, for a change nobody made.
 *
 * That invariant is held by construction rather than by care: a pill is a
 * `TextNode` whose text IS `@name`, so `root.getTextContent()` is the string.
 * There is no serialiser to keep in step, which is the only reason this is a
 * safe thing to put in front of a hashed payload.
 *
 * ## Two ways in, and neither has to be taught
 *
 * Type the citation — `Pillify` turns it into a pill once the caret has moved
 * on — or take it from the menu that opens on `@`. The menu is the shortcut,
 * not the entrance, which is what the hand-rolled version got wrong: it was
 * the only way in, and it was a key combination with nothing on screen to
 * name it.
 *
 * ## Reusable on purpose
 *
 * It takes its tokens as a prop and knows nothing about reference angles, so a
 * run's prompt editor can hand it a different list.
 */
export const FAMILY = { mono: "font-mono text-sm", body: "font-body text-base" } as const;

export function TokenizedPromptEditor({
  value,
  onValueChange,
  tokens,
  ariaLabel,
  placeholder = "Write the prompt… type @ to cite a block or a character.",
  className = "rounded-md border border-line p-2",
  contentClassName = "min-h-24",
  onSubmit,
  focusKey,
  blurKey,
  family = "mono",
  menuSide = "down",
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
   * ⌘/Ctrl+Enter sends. Plain Enter breaks the line, as does Shift+Enter.
   *
   * Only when given: the template editor has no send at all, because a
   * template is paragraphs. The create bar did send on plain Enter, like a
   * chat box — and a prompt is not a chat message: it is paragraphs too, and
   * a line break meant for the prompt sent it half-written (decision
   * 2026-09-13). The `@` menu still takes Enter first while it is open.
   */
  onSubmit?: () => void;
  /**
   * `mono` for a template — a document a person reads character by character,
   * placeholders and all. `body` for the create sheet, where the prompt is a
   * sentence typed into a chat box and mono reads as a terminal.
   */
  family?: "mono" | "body";
  /**
   * Which way the `@` menu opens. Lexical hangs it under the caret and flips
   * it upward only when the EDITOR is taller than the menu — a two-line box
   * at the foot of the viewport never is, so the menu ran off the bottom of
   * the screen. The create sheet says `up`.
   */
  menuSide?: "down" | "up";
  /** Focus the editor whenever this changes. What "load a run into the bar" does. */
  focusKey?: number;
  /**
   * Bump to take focus OUT of the editor. A plain `.blur()` on the element
   * does not hold: Lexical keeps its selection and puts focus back when the
   * next update commits (`$updateDOMSelection`), so leaving has to go through
   * `editor.blur()`, which drops the selection first.
   */
  blurKey?: number;
}) {
  /** The names a typed citation becomes a pill for — see `nextKnown`. */
  const known = useMemo(() => new Set(tokens.map((t) => t.name)), [tokens]);

  /**
   * Whether the `@` menu is open — read by the Enter handler, which must yield
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
                className={`${contentClassName} whitespace-pre-wrap ${FAMILY[family]} leading-6 outline-none`}
              />
            }
            placeholder={
              <span className={`pointer-events-none absolute inset-x-0 top-0 truncate ${FAMILY[family]} leading-6 text-muted`}>
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
        <Pillify known={known} />
        {onSubmit && <SubmitOnEnter onSubmit={onSubmit} menuOpen={menuOpen} />}
        <Focus focusKey={focusKey} />
        <Blur blurKey={blurKey} />
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
        <Typeahead tokens={tokens} menuOpen={menuOpen} menuSide={menuSide} />
      </div>
    </LexicalComposer>
  );
}

/**
 * ⌘/Ctrl+Enter sends; Enter and Shift+Enter are line breaks.
 *
 * Registered at `COMMAND_PRIORITY_HIGH`, above the `@` menu's own Enter and
 * above the plain-text plugin's, so it is asked first — and it declines when
 * the menu is open, so the keystroke falls through to the menu and picks the
 * highlighted pill instead of sending a half-written citation. It declines
 * without the modifier too, which leaves the newline to the plugin that
 * always drew one. `metaKey` is ⌘ on a Mac; `ctrlKey` is Ctrl everywhere else.
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
          if (
            event === null ||
            !(event.metaKey || event.ctrlKey) ||
            event.shiftKey ||
            event.isComposing ||
            menuOpen.current
          )
            return false;
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

/** Leave the editor when asked to — a press outside the bar asks. */
function Blur({ blurKey }: { blurKey: number | undefined }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (blurKey === undefined || blurKey === 0) return;
    // `editor.blur()` alone does not hold: it takes the DOM selection away
    // but the editor state keeps its own, and the next commit's
    // `$updateDOMSelection` puts the DOM selection — and focus — back to
    // match. Drop the state's selection first, so there is nothing to restore.
    editor.update(() => $setSelection(null), { discrete: true });
    editor.blur();
  }, [editor, blurKey]);

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
 * An `@citation` becomes a pill — whether typed, pasted or loaded.
 *
 * **The only place text becomes a pill.** `Hydrate` puts the stored string in as
 * plain text and this turns it into pills, so a prompt read from the API and a
 * prompt typed by hand go through exactly the same code.
 *
 * **This is what makes the menu optional rather than mandatory.** Lexical's own
 * `registerLexicalTextEntity` is the shape of this and is deliberately not used:
 * its transform converts a target node back to plain text whenever the node
 * beside it is a text entity or its mode is not normal, which would un-pill both
 * of two ADJACENT placeholders, and would un-pill anything the moment you typed
 * a character after it, because these nodes are in `token` mode. No reverse
 * transform is needed here for the same reason: token mode means the caret
 * cannot get inside a pill, so a pill's text cannot stop matching.
 *
 * ## Not under the caret
 *
 * A brace said when a name was finished; an `@` does not. `@block.light` is a
 * known name and also the first eleven characters of `@block.light_soft`, so a
 * citation that ends exactly where the caret is may still be being typed and
 * is left alone — the menu is open over it anyway, and Enter there makes the
 * pill directly. It becomes a pill the moment the caret moves on: a space or a
 * full stop dirties the node and the transform runs again; a click or an
 * arrow elsewhere dirties it by hand, below, because a selection change on its
 * own does not.
 */
function Pillify({ known }: { known: ReadonlySet<string> }) {
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
        const text = node.getTextContent();
        const found = nextKnown(text, known);
        if (found === null) return;
        if (found.end === text.length) {
          const selection = $getSelection();
          if (
            $isRangeSelection(selection) &&
            selection.isCollapsed() &&
            selection.anchor.key === node.getKey() &&
            selection.anchor.offset === text.length
          )
            return;
        }
        // One per pass. Lexical re-runs a transform until nothing is dirty, and
        // the remainder left by the split is dirty, so a line pasted with six
        // placeholders resolves without looping here.
        const target =
          found.start === 0
            ? node.splitText(found.end)[0]
            : node.splitText(found.start, found.end)[1];
        target?.replace($createTokenNode(`@${found.name}`, found.namespace));
      }),
    [editor, known],
  );

  // The node the caret just left, marked dirty so the transform above gets a
  // second look at a citation it deferred. Only text nodes, and only when the
  // anchor actually moved to another node — the transform is cheap, but a
  // dirty mark on every keystroke is a rebuild on every keystroke.
  useEffect(() => {
    let last: string | null = null;
    return editor.registerCommand(
      SELECTION_CHANGE_COMMAND,
      () => {
        const selection = $getSelection();
        const key = $isRangeSelection(selection) ? selection.anchor.key : null;
        if (last !== null && last !== key) {
          const left = $getNodeByKey(last);
          if ($isTextNode(left) && left.isSimpleText()) left.markDirty();
        }
        last = key;
        return false;
      },
      COMMAND_PRIORITY_LOW,
    );
  }, [editor]);

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
 * The menu that opens on `@`.
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
  menuOpen,
  menuSide,
}: {
  tokens: PromptToken[];
  /** Written here, read by `SubmitOnEnter` — the one thing the two share. */
  menuOpen: MutableRefObject<boolean>;
  menuSide: "down" | "up";
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
        .filter((t) =>
          t.name.toLowerCase().includes((query ?? "").toLowerCase()),
        )
        .slice(0, 8)
        .map((token) => new TokenOption(token)),
    [query, tokens],
  );

  useEffect(() => {
    menuOpen.current = resolved && options.length > 0;
  }, [menuOpen, options.length, resolved]);

  // `promptTriggerMatch`, not a second copy of it. There WAS a second copy, and
  // when the regex grew a leading boundary group, that copy went on reading
  // group 1 — which had become the character BEFORE the trigger. At the start
  // of a node the query was therefore always empty and the menu never
  // narrowed; in the middle of a paragraph it was the preceding space, which
  // matches no placeholder, so no menu opened at all.
  const trigger = useCallback(
    (text: string): MenuTextMatch | null => promptTriggerMatch(text),
    [],
  );

  const select = useCallback(
    (
      option: TokenOption,
      nodeToReplace: TextNode | null,
      closeMenu: () => void,
    ) => {
      editor.update(() => {
        const [namespace] = citationsIn(`@${option.token.name}`);
        if (!namespace) return;
        const pill = $createTokenNode(`@${option.token.name}`, namespace.namespace);
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
    [editor],
  );

  return (
    <LexicalTypeaheadMenuPlugin<TokenOption>
      options={options}
      onQueryChange={setQuery}
      onSelectOption={select}
      onOpen={onOpen}
      onClose={onClose}
      triggerFn={trigger}
      // An `@` typed immediately after a pill is the commonest case there is —
      // a template is mostly citations — and the default suppresses the menu
      // when the caret sits against a text entity, which every pill is.
      ignoreEntityBoundary
      // Lexical hangs the anchor off `<body>`, `position: absolute` and no
      // z-index, so it painted under the create card (`z-[25]`): the menu's
      // top rows were behind the card's bottom edge. The top overlay tier.
      anchorClassName="z-50"
      menuRenderFn={(
        anchorElementRef,
        { selectedIndex, selectOptionAndCleanUp, setHighlightedIndex },
      ) =>
        anchorElementRef.current === null || options.length === 0
          ? null
          : createPortal(
              // Frosted, like the create sheet: it floats over the prose it
              // is about to add to, and a solid card there is a hole in the
              // page. `bg-sheet` over `backdrop-blur-xl`, the same recipe.
              <ul
                role="listbox"
                aria-label="Insert a placeholder"
                className={`m-0 max-h-64 w-80 list-none overflow-auto rounded-md bg-sheet p-1
                            shadow-[0_8px_32px_rgba(0,0,0,0.55)] ring-1 ring-line backdrop-blur-xl ${
                  // Above the anchor, which Lexical puts just under the caret
                  // line; the margin clears that line.
                  menuSide === "up" ? "absolute bottom-full left-0 mb-7" : ""
                }`}
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
                    className={`flex cursor-pointer items-baseline gap-2 rounded-sm px-2 py-1 ${
                      selectedIndex === index ? "bg-fill-hover" : ""
                    }`}
                  >
                    {/* In the tint its pill will have. */}
                    <span
                      className={`font-mono text-sm ${CITE_TEXT[citationsIn(`@${option.token.name}`)[0]?.namespace ?? "block"]}`}
                    >
                      {`@${option.token.name}`}
                    </span>
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

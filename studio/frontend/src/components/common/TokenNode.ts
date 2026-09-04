import { $applyNodeReplacement, TextNode } from "lexical";
import type { EditorConfig, NodeKey, SerializedTextNode } from "lexical";

/**
 * A `{placeholder}` in a prompt template, drawn as a pill and treated as one thing.
 *
 * ## Why it subclasses TextNode rather than being a decorator
 *
 * **Because the serialiser then does not exist.** The stored value is a plain
 * string — assembly is `string.Formatter().vformat` over `{name}`, and the
 * prompt is hashed into the fingerprint, so the editor has to give back
 * exactly the characters it was given, byte for byte. A decorator node holds
 * arbitrary React and needs a hand-written serialiser, which is a second
 * description of the string and a place for a normalised space to creep in;
 * every duplicate check would then miss over a change nobody made.
 *
 * A `TextNode` whose text IS `{name}` needs none of that. `root.getTextContent()`
 * returns the original string, line breaks included, because that is simply what
 * the nodes hold.
 *
 * ## Why `token` mode
 *
 * Lexical's `'token'` mode makes a text node atomic: the caret will not enter
 * it, and a backspace at its edge removes the whole thing. That is exactly the
 * behaviour wanted, and getting it from the framework rather than from a keydown
 * handler means there is no half-deleted state to guard against — a `{face_onl}`
 * is a placeholder nothing provides, and nothing would say so until the angle
 * was drafted and refused.
 */
export class TokenNode extends TextNode {
  /** `block` is editable and shared; `computed` is filled per character. */
  __kind: "block" | "computed";

  static getType(): string {
    return "prompt-token";
  }

  static clone(node: TokenNode): TokenNode {
    return new TokenNode(node.__text, node.__kind, node.__key);
  }

  constructor(text: string, kind: "block" | "computed", key?: NodeKey) {
    super(text, key);
    this.__kind = kind;
  }

  createDOM(config: EditorConfig): HTMLElement {
    const dom = super.createDOM(config);
    // Two kinds, and they must not look alike. A block is in the database and
    // opens for editing; a computed value is filled from the character's bible
    // and has nothing behind it to open. Identical pills would send somebody
    // clicking `{top}` looking for a text box that cannot exist.
    dom.className =
      this.__kind === "block"
        ? "rounded border border-primary bg-surface-alt px-1 font-mono text-primary"
        : "rounded border border-dashed border-line bg-surface-alt px-1 font-mono text-muted";
    dom.dataset.token = this.__text.slice(1, -1);
    dom.dataset.kind = this.__kind;
    return dom;
  }

  updateDOM(prev: this, dom: HTMLElement, config: EditorConfig): boolean {
    if (prev.__kind !== this.__kind) return true;
    return super.updateDOM(prev, dom, config);
  }

  static importJSON(json: SerializedTextNode & { kind?: "block" | "computed" }): TokenNode {
    return $createTokenNode(json.text, json.kind ?? "block");
  }

  exportJSON(): SerializedTextNode & { kind: "block" | "computed" } {
    return { ...super.exportJSON(), type: "prompt-token", kind: this.__kind };
  }

  /**
   * **Not editable, and that is the point.** A pill's text IS the citation, so
   * letting somebody type inside it produces a placeholder nothing provides.
   * Editing what a block SAYS happens on the block, where the fact that it is
   * shared by fourteen angles can be stated first.
   */
  isTextEntity(): boolean {
    return true;
  }
}

export function $createTokenNode(text: string, kind: "block" | "computed"): TokenNode {
  const node = new TokenNode(text, kind);
  node.setMode("token");
  return $applyNodeReplacement(node);
}

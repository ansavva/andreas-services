import { $applyNodeReplacement, TextNode } from "lexical";
import type { EditorConfig, NodeKey, SerializedTextNode } from "lexical";

import type { Namespace } from "../../utils/citations";
import { CITE_PILL } from "./citeStyle";

/**
 * An `@citation` in a prompt template, drawn as a pill and treated as one thing.
 *
 * ## Why it subclasses TextNode rather than being a decorator
 *
 * **Because the serialiser then does not exist.** The stored value is a plain
 * string — the API fills it by scanning for `@name`, and the prompt is hashed
 * into the fingerprint, so the editor has to give back exactly the characters
 * it was given, byte for byte. A decorator node holds arbitrary React and
 * needs a hand-written serialiser, which is a second description of the
 * string and a place for a normalised space to creep in; every duplicate check
 * would then miss over a change nobody made.
 *
 * A `TextNode` whose text IS `@name` needs none of that. `root.getTextContent()`
 * returns the original string, line breaks included, because that is simply what
 * the nodes hold.
 *
 * ## Why `token` mode
 *
 * Lexical's `'token'` mode makes a text node atomic: the caret will not enter
 * it, and a backspace at its edge removes the whole thing. That is exactly the
 * behaviour wanted, and getting it from the framework rather than from a keydown
 * handler means there is no half-deleted state to guard against — a
 * `@block.face_onl` is a placeholder nothing provides, and nothing would say so
 * until the template was drafted and refused.
 *
 * ## The tint is the one hue the chrome has
 *
 * A pill is a faint fill and a text tint of one muted hue — the one place
 * this app puts colour on chrome. A block is the full tint at medium weight; a
 * computed value (the character's bible, the slot the images landed in) is
 * the same tint stepped back. `citeStyle.ts` holds the classes;
 * `styles/app.css` holds the reasoning. The text says the namespace too, so
 * the tint is never the only carrier.
 */
export class TokenNode extends TextNode {
  __namespace: Namespace;

  static getType(): string {
    return "prompt-token";
  }

  static clone(node: TokenNode): TokenNode {
    return new TokenNode(node.__text, node.__namespace, node.__key);
  }

  constructor(text: string, namespace: Namespace, key?: NodeKey) {
    super(text, key);
    this.__namespace = namespace;
  }

  createDOM(config: EditorConfig): HTMLElement {
    const dom = super.createDOM(config);
    dom.className = CITE_PILL[this.__namespace];
    dom.dataset.token = this.__text.slice(1);
    dom.dataset.namespace = this.__namespace;
    return dom;
  }

  updateDOM(prev: this, dom: HTMLElement, config: EditorConfig): boolean {
    if (prev.__namespace !== this.__namespace) return true;
    return super.updateDOM(prev, dom, config);
  }

  static importJSON(json: SerializedTextNode & { namespace?: Namespace }): TokenNode {
    return $createTokenNode(json.text, json.namespace ?? "block");
  }

  exportJSON(): SerializedTextNode & { namespace: Namespace } {
    return { ...super.exportJSON(), type: "prompt-token", namespace: this.__namespace };
  }

  /**
   * **Not editable, and that is the point.** A pill's text IS the citation, so
   * letting somebody type inside it produces a placeholder nothing provides.
   * Editing what a block SAYS happens on the block, where the fact that it is
   * shared by fourteen templates can be stated first.
   */
  isTextEntity(): boolean {
    return true;
  }
}

/** A pill for `text`, which is `@` plus a citation's name. */
export function $createTokenNode(text: string, namespace: Namespace): TokenNode {
  const node = new TokenNode(text, namespace);
  node.setMode("token");
  return $applyNodeReplacement(node);
}

/** The literal glyphs a button used to carry, before `icons.tsx` had one. */
const GLYPHS = new Set(["↑", "↓", "←", "→", "▾", "▸", "×", "…"]);

function isMeaningful(child) {
  if (child.type === "JSXText") return child.value.trim().length > 0;
  return true;
}

function glyphTextOf(child) {
  if (child.type === "JSXText") return child.value.trim();
  if (
    child.type === "JSXExpressionContainer" &&
    child.expression.type === "Literal" &&
    typeof child.expression.value === "string"
  ) {
    return child.expression.value.trim();
  }
  return null;
}

/**
 * A button whose only child is one of these characters is drawing its own
 * icon out of text. `components/common/icons.tsx` has an SVG for all eight —
 * an arrow, a caret, a close mark, an ellipsis — and a real icon survives a
 * font substitution that a glyph does not.
 */
export default {
  meta: {
    type: "problem",
    docs: { description: "A lone glyph character as a button's only child should be an SVG icon." },
    schema: [],
  },
  create(context) {
    function check(node) {
      const children = node.children.filter(isMeaningful);
      if (children.length !== 1) return;
      const text = glyphTextOf(children[0]);
      if (text !== null && GLYPHS.has(text)) {
        context.report({
          node: children[0],
          message: "Glyphs are icons from components/common/icons.tsx.",
        });
      }
    }

    return {
      JSXElement(node) {
        const name = node.openingElement.name;
        if (name.type !== "JSXIdentifier") return;
        if (name.name === "button" || /Button$/.test(name.name)) check(node);
      },
    };
  },
};

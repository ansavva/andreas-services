function textOf(children) {
  return children
    .map((child) => {
      if (child.type === "JSXText") return child.value;
      if (
        child.type === "JSXExpressionContainer" &&
        child.expression.type === "Literal" &&
        typeof child.expression.value === "string"
      ) {
        return child.expression.value;
      }
      if (child.type === "JSXExpressionContainer" && child.expression.type === "TemplateLiteral") {
        return child.expression.quasis.map((quasi) => quasi.value.raw).join("");
      }
      return "";
    })
    .join("")
    .trim();
}

/**
 * "No X yet." and "Nothing Y." are `EmptyState`'s sentence, not a bare `Text`
 * dropped wherever a listing came back empty — that is how the app ended up
 * with a dozen slightly different ways to say the same thing. Scoped OFF
 * `EmptyState.tsx` itself in `eslint.config.js`, which is where the sentence
 * is allowed to live.
 */
export default {
  meta: {
    type: "problem",
    docs: { description: "Empty-state prose belongs in EmptyState, not a bare Text." },
    schema: [],
  },
  create(context) {
    return {
      JSXElement(node) {
        const name = node.openingElement.name;
        if (name.type !== "JSXIdentifier" || name.name !== "Text") return;
        const text = textOf(node.children);
        if (text.startsWith("No ") || text.startsWith("Nothing ")) {
          context.report({ node, message: "Use EmptyState." });
        }
      },
    };
  },
};

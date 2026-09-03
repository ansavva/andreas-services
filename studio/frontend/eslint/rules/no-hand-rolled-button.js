import { buildConstMap, classStringsFromJSXAttribute } from "../utils/classStrings.js";

function looksLikeAStyledControl(text) {
  return text.includes("border") || text.includes("hover:");
}

/**
 * A raw `<button className="...border...">` or `hover:...` outside
 * `components/common/` is a control drawn by hand instead of reached for —
 * `Button`, `IconButton` or `buttonClass`. Scoped OFF `components/common/` in
 * `eslint.config.js`, because that is where the design-system-wrapping
 * helpers (`Chip`, `TagSelect`, `Backlinks`, …) live and are allowed to build
 * one. A genuinely structural raw button elsewhere — a listing row that is
 * itself the click target, a full-bleed poster play button — gets an
 * `eslint-disable-next-line` naming why, not a rewrite into a component that
 * does not fit the shape.
 */
export default {
  meta: {
    type: "problem",
    docs: { description: "A hand-rolled <button> styled like a control, outside components/common/." },
    schema: [],
  },
  create(context) {
    let constMap = new Map();

    return {
      Program(node) {
        constMap = buildConstMap(node);
      },
      JSXOpeningElement(node) {
        if (node.name.type !== "JSXIdentifier" || node.name.name !== "button") return;
        const classAttr = node.attributes.find(
          (attr) =>
            attr.type === "JSXAttribute" &&
            attr.name.type === "JSXIdentifier" &&
            (attr.name.name === "className" || attr.name.name === "class"),
        );
        if (!classAttr) return;
        const strings = classStringsFromJSXAttribute(classAttr, constMap);
        if (strings.some(({ text }) => looksLikeAStyledControl(text))) {
          context.report({
            node,
            message: "Use Button, IconButton or buttonClass from the design system.",
          });
        }
      },
    };
  },
};

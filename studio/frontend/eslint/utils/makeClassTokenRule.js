import { buildConstMap, classStrings, classStringsFromJSXAttribute, CLASS_FUNCTIONS } from "./classStrings.js";

/**
 * A rule that flags any class-bearing string — a JSX `className`/`class`, or
 * a string argument to `buttonClass`/`iconButtonClass`/`chipClass`/`clsx`/
 * `twMerge`/`cn` — matching `test`, reporting `message` once per attribute or
 * argument. Shared by the corner-radius and neutral-ramp rules, which differ
 * only in what they are looking for.
 */
export function makeClassTokenRule({ description, test, message }) {
  return {
    meta: {
      type: "problem",
      docs: { description },
      schema: [],
    },
    create(context) {
      let constMap = new Map();

      function scan(pairs) {
        for (const { text, node } of pairs) {
          if (test(text)) {
            context.report({ node, message });
            return;
          }
        }
      }

      return {
        Program(node) {
          constMap = buildConstMap(node);
        },
        JSXAttribute(node) {
          if (node.name.type !== "JSXIdentifier") return;
          if (node.name.name !== "className" && node.name.name !== "class") return;
          scan(classStringsFromJSXAttribute(node, constMap));
        },
        CallExpression(node) {
          const name = node.callee.type === "Identifier" ? node.callee.name : null;
          if (!name || !CLASS_FUNCTIONS.has(name)) return;
          for (const arg of node.arguments) scan(classStrings(arg, constMap));
        },
      };
    },
  };
}

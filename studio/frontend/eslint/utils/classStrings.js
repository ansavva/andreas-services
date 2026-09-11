/**
 * Statically extracting Tailwind class strings from an expression.
 *
 * A class list in this codebase is almost never a bare string literal — it is
 * a template literal with a ternary spliced in, a `buttonClass({...})` call,
 * or a named constant referenced from three files. The
 * vocabulary rules need every one of those shapes, so this walks the parts an
 * `eslint-plugin`-free rule can still reason about: literals, template
 * quasis, both sides of `? :` and `&&`/`||`, array and object members (for
 * `clsx`'s forms), the arguments of a recognized class-building call, and a
 * same-module `const` an identifier resolves to. What it does NOT attempt is
 * real scope/type analysis — a re-exported or reassigned constant is missed,
 * which only means a rule stays silent, never that it misfires.
 */

/** Functions in this codebase whose string arguments are Tailwind classes. */
export const CLASS_FUNCTIONS = new Set([
  "buttonClass",
  "iconButtonClass",
  "chipClass",
  "linkButtonClass",
  "clsx",
  "twMerge",
  "cn",
]);

/** Every top-level `const NAME = <expr>` in the module, by name. */
export function buildConstMap(program) {
  const map = new Map();
  for (const stmt of program.body) {
    if (stmt.type !== "VariableDeclaration" || stmt.kind !== "const") continue;
    for (const decl of stmt.declarations) {
      if (decl.id.type === "Identifier" && decl.init) {
        map.set(decl.id.name, decl.init);
      }
    }
  }
  return map;
}

function collect(node, out, constMap, seen) {
  if (!node) return;
  switch (node.type) {
    case "Literal":
      if (typeof node.value === "string") out.push({ text: node.value, node });
      break;
    case "TemplateLiteral":
      for (const quasi of node.quasis) {
        if (quasi.value.raw) out.push({ text: quasi.value.raw, node: quasi });
      }
      for (const expr of node.expressions) collect(expr, out, constMap, seen);
      break;
    case "ConditionalExpression":
      collect(node.consequent, out, constMap, seen);
      collect(node.alternate, out, constMap, seen);
      break;
    case "LogicalExpression":
      collect(node.left, out, constMap, seen);
      collect(node.right, out, constMap, seen);
      break;
    case "ArrayExpression":
      for (const element of node.elements) collect(element, out, constMap, seen);
      break;
    case "ObjectExpression":
      for (const prop of node.properties) {
        if (prop.type !== "Property") continue;
        if (prop.key.type === "Literal" && typeof prop.key.value === "string") {
          out.push({ text: prop.key.value, node: prop.key });
        } else if (prop.key.type === "Identifier" && !prop.computed) {
          out.push({ text: prop.key.name, node: prop.key });
        }
        collect(prop.value, out, constMap, seen);
      }
      break;
    case "CallExpression": {
      const name = node.callee.type === "Identifier" ? node.callee.name : null;
      if (name && CLASS_FUNCTIONS.has(name)) {
        for (const arg of node.arguments) collect(arg, out, constMap, seen);
      }
      break;
    }
    case "Identifier": {
      if (!constMap || !constMap.has(node.name) || seen.has(node.name)) break;
      seen.add(node.name);
      collect(constMap.get(node.name), out, constMap, seen);
      break;
    }
    default:
      break;
  }
}

/** Every `{ text, node }` a class-bearing expression could statically produce. */
export function classStrings(node, constMap) {
  const out = [];
  collect(node, out, constMap ?? null, new Set());
  return out;
}

/** The same, starting from a JSX `className`/`class` attribute. */
export function classStringsFromJSXAttribute(attr, constMap) {
  if (!attr.value) return [];
  if (attr.value.type === "Literal") return classStrings(attr.value, constMap);
  if (attr.value.type === "JSXExpressionContainer") {
    return classStrings(attr.value.expression, constMap);
  }
  return [];
}

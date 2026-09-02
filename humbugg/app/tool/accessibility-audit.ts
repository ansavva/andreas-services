// Accessibility rules this codebase enforces on itself (#138).
//
// These read the source rather than render it, in the spirit of the backend's
// CiSmokeEnvironmentTests: some mistakes are invisible at runtime and obvious in a grep, and the
// cheapest place to catch them is a check that names the rule.
//
// It lives in `tool/` rather than beside the jest suite for the reason `tsconfig.json` gives at
// length: a source scanner needs `node:fs`, and putting `@types/node` in scope to satisfy one test
// would put `process` and `Buffer` in scope for every React Native component in the app — where
// they typecheck cleanly and fail on a device. `npm run a11y:check` runs it on every PR, next to
// `brand:check`, which is here for the same reason.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

const SRC = path.join(import.meta.dirname, '..', 'src');

function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx') && !entry.endsWith('.test.tsx')) found.push(full);
    }
  };
  walk(SRC);
  return found;
}

/**
 * An `aria-label` on a control inside `FieldLabel` is silently ignored.
 *
 * `FieldLabel` wraps the design system's `Field.Root`, whose native leaf gives the label `Text` a
 * `nativeID` and points the control at it with `aria-labelledby`. That association wins, so the
 * `aria-label` next to it does nothing — and the trap is that it LOOKS like the working pattern, so
 * it gets copied. Eighteen had accumulated by the time this check was written, and following the
 * pattern cost three separate mistakes in one afternoon: tests fail with "unable to find an
 * element" naming a label that is plainly on the screen.
 *
 * The accessible name is the label text, so put everything a screen reader should say in `label` —
 * including "(optional)", the way `wishlist.tsx` does with "Link (optional)".
 */
function inertLabels(file: string, source: string): string[] {
  const found: string[] = [];
  for (const block of source.matchAll(/<FieldLabel\b[\s\S]*?<\/FieldLabel>/g)) {
    for (const label of block[0].matchAll(/aria-label="([^"]*)"/g)) {
      found.push(`${rel(file)}: aria-label="${label[1]}" inside a FieldLabel does nothing`);
    }
  }
  return found;
}

/**
 * Every control that is NOT inside a `FieldLabel` needs an accessible name of its own.
 *
 * A bare `Input`, `Select`, `Switch` or `Textarea` has no label element to be associated with, so
 * without `aria-label` a screen reader announces it as an unnamed text field. `FieldLabel` is the
 * preferred shape; this catches the ones that skipped it.
 */
function unnamedControls(file: string, source: string): string[] {
  const found: string[] = [];
  // FieldLabel blocks are blanked out: those controls are named by their label text.
  const outside = source.replace(/<FieldLabel\b[\s\S]*?<\/FieldLabel>/g, '');
  const opening = /<(Input|Textarea|Select|DateInput|Switch\.Root|Checkbox\.Root)\b/g;
  for (const match of outside.matchAll(opening)) {
    const props = openingTag(outside, match.index + match[0].length);
    if (!/aria-label=/.test(props) && !/accessibilityLabel=/.test(props)) {
      found.push(`${rel(file)}: <${match[1]}> has no accessible name`);
    }
  }
  return found;
}

/**
 * The props of one JSX opening tag, read by scanning rather than by regex.
 *
 * A lazy `[\s\S]*?>` stops at the first `>` it sees, and in this codebase that is nearly always the
 * one inside an `onCheckedChange={(checked) => …}` arrow — so every control with a handler looked
 * unnamed. Tracking brace depth is what makes the difference between a rule and a nuisance.
 */
function openingTag(source: string, from: number): string {
  let depth = 0;
  for (let index = from; index < source.length; index++) {
    const character = source[index];
    if (character === '{') depth++;
    else if (character === '}') depth--;
    else if (character === '>' && depth === 0 && source[index - 1] !== '=') {
      return source.slice(from, index);
    }
  }
  return source.slice(from);
}

/** Line comments only — enough to stop a `<Input>` mentioned in prose counting as code. */
function stripComments(source: string): string {
  return source
    .split('\n')
    .map((line) => (line.trimStart().startsWith('//') ? '' : line))
    .join('\n');
}

const rel = (file: string) => path.relative(SRC, file);

const problems = sourceFiles().flatMap((file) => {
  const source = stripComments(readFileSync(file, 'utf8'));
  return [...inertLabels(file, source), ...unnamedControls(file, source)];
});

if (problems.length > 0) {
  console.error(`${problems.length} accessibility problem(s):\n`);
  for (const problem of problems) console.error(`  ${problem}`);
  console.error('\nSee tool/accessibility-audit.ts for what each rule means.');
  process.exit(1);
}

console.log(`No accessibility problems in ${sourceFiles().length} source files.`);

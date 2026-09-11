// Writes classroom's brand into the Cognito Managed Login style document.
//
// The sign-in, forced-new-password, reset and MFA pages are Cognito's, not
// ours — they cannot load `app.css`, only a style document handed to AWS. This
// keeps that document in step with the stylesheet the app actually paints with,
// so a teacher does not meet a different product at the door.
//
// `managed-login-settings.json` IS GENERATED — do not hand-edit it. JSON has no
// comment syntax and AWS rejects unknown keys, so the file cannot carry its own
// banner; this comment is it.
//
// Its STRUCTURE is AWS's schema, exported from a live branding record with
//   aws cognito-idp describe-managed-login-branding-by-client \
//     --user-pool-id <pool> --client-id <client> --return-merged-resources \
//     --query 'ManagedLoginBranding.Settings'
// To change LAYOUT, edit in the Cognito console's branding editor, re-export
// with that command, commit, then re-run `npm run brand` to put the token
// values back over whatever the console wrote.
//
// ## How this differs from studio's version, which it is a port of
//
// Studio's stylesheet declares its whole palette, so reading one file is
// enough. Classroom's declares only what it OVERRIDES — the green, the warm
// greys, the radii — and inherits the rest from the design system's shipped
// `theme.css`. So this reads both, in that order, and the override wins. That
// also means a design-system bump can move these colours, which is correct:
// the hosted page should follow the app, and `npm run brand:check` in CI is
// what makes the drift visible instead of silent.
//
// NO ASSETS. Classroom has no logo, so `form.logo` stays disabled and Cognito
// keeps its own illustrations off. When there is one it lands in the Terraform
// as an `asset` block — note that adding one is ForceNew on the branding
// resource, which briefly leaves the domain without a style.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE_CSS = resolve(HERE, '../node_modules/@ansavva/design-system/src/styles/theme.css');
const APP_CSS = resolve(HERE, '../src/styles/app.css');
const OUT = resolve(HERE, '../../infra/modules/auth/managed-login-settings.json');
const REGEN = 'npm run brand';

type Values = Record<string, string>;

/** Which Cognito colour slot each semantic role fills. `{mode}` → light/dark. */
const SLOTS: ReadonlyArray<readonly [string, string]> = [
  ['components.primaryButton.{mode}.defaults.backgroundColor', 'primary'],
  ['components.primaryButton.{mode}.defaults.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.hover.backgroundColor', 'primaryHover'],
  ['components.primaryButton.{mode}.hover.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.active.backgroundColor', 'primaryActive'],
  ['components.primaryButton.{mode}.active.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.disabled.backgroundColor', 'muted'],
  ['components.primaryButton.{mode}.disabled.borderColor', 'muted'],
  ['components.secondaryButton.{mode}.defaults.backgroundColor', 'card'],
  ['components.secondaryButton.{mode}.defaults.borderColor', 'line'],
  ['components.secondaryButton.{mode}.defaults.textColor', 'ink'],
  ['components.secondaryButton.{mode}.hover.backgroundColor', 'surfaceAlt'],
  ['components.secondaryButton.{mode}.hover.borderColor', 'ink'],
  ['components.secondaryButton.{mode}.hover.textColor', 'ink'],
  ['components.secondaryButton.{mode}.active.backgroundColor', 'surfaceAlt'],
  ['components.secondaryButton.{mode}.active.borderColor', 'ink'],
  ['components.secondaryButton.{mode}.active.textColor', 'ink'],
  ['components.pageBackground.{mode}.color', 'bg'],
  ['components.form.{mode}.backgroundColor', 'card'],
  ['components.form.{mode}.borderColor', 'line'],
  ['components.pageText.{mode}.headingColor', 'ink'],
  ['components.pageText.{mode}.bodyColor', 'ink'],
  ['components.pageText.{mode}.descriptionColor', 'muted'],
  ['componentClasses.input.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.input.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.input.{mode}.placeholderColor', 'muted'],
  ['componentClasses.inputLabel.{mode}.textColor', 'ink'],
  ['componentClasses.inputDescription.{mode}.textColor', 'muted'],
  // The focus ring. `primary` is a light mint here, which is legible as a ring
  // on the warm background but would be invisible as one on the button it sits
  // inside — Cognito draws this on the INPUT, so it is the right role.
  ['componentClasses.focusState.{mode}.borderColor', 'primary'],
  ['componentClasses.divider.{mode}.borderColor', 'line'],
  ['componentClasses.link.{mode}.defaults.textColor', 'ink'],
  ['componentClasses.link.{mode}.hover.textColor', 'muted'],
  ['componentClasses.optionControls.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.optionControls.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.optionControls.{mode}.selected.backgroundColor', 'primary'],
  ['componentClasses.optionControls.{mode}.selected.foregroundColor', 'primaryText'],
  ['componentClasses.dropDown.{mode}.defaults.itemBackgroundColor', 'card'],
  ['componentClasses.dropDown.{mode}.hover.itemBackgroundColor', 'surfaceAlt'],
  ['componentClasses.dropDown.{mode}.hover.itemBorderColor', 'line'],
  ['componentClasses.dropDown.{mode}.hover.itemTextColor', 'ink'],
  ['componentClasses.dropDown.{mode}.match.itemTextColor', 'ink'],
  ['componentClasses.statusIndicator.{mode}.error.indicatorColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.error.borderColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.success.indicatorColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.success.borderColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.warning.indicatorColor', 'warning'],
  ['componentClasses.statusIndicator.{mode}.warning.borderColor', 'warning'],
  ['components.alert.{mode}.error.borderColor', 'danger'],
];

/**
 * Corners, from the same `--radius-*` properties the app uses.
 *
 * Cognito wants a NUMBER of pixels, so `--radius-pill` cannot be expressed here
 * — the buttons on the hosted page are the one place classroom's pills do not
 * reach, because AWS's schema has no such value. `lg` is the closest honest
 * answer and is what the app's cards use.
 */
const RADII: ReadonlyArray<readonly [string, string]> = [
  ['componentClasses.buttons.borderRadius', 'lg'],
  ['componentClasses.input.borderRadius', 'sm'],
  ['componentClasses.dropDown.borderRadius', 'sm'],
  ['components.form.borderRadius', 'lg'],
  ['components.alert.borderRadius', 'md'],
];

/**
 * Structural choices that are OURS, not AWS's defaults. Each defaults the wrong
 * way in a merged export and each is invisible until someone looks at the page:
 *
 * - `colorSchemeMode` — classroom is light-only (`color-scheme: light` in
 *   app.css, and the package's dark mode is opt-in and never opted into). A
 *   dark sign-in page would be a different product from the one behind it.
 * - `pageBackground.image.enabled` ships TRUE, and with no background asset of
 *   our own Cognito fills it with its own pastel gradient, which covers the
 *   brand background entirely.
 * - `form.logo.enabled` — no logo yet. Stated rather than left to the default
 *   so it reads as a decision.
 */
const STRUCTURE: ReadonlyArray<readonly [string, string | boolean]> = [
  ['categories.global.colorSchemeMode', 'LIGHT'],
  ['components.pageBackground.image.enabled', false],
  ['components.form.logo.enabled', false],
];

/** `--color-primary-text` → `primaryText`; `--radius-lg` → `lg`. */
function roleName(property: string, prefix: string): string {
  return property.replace(prefix, '').replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
}

/** Cognito wants `rrggbbaa`, no leading `#`, lower-cased so diffs are stable. */
function cognitoColor(rgba: readonly [number, number, number, number]): string {
  return rgba.map((n) => Math.round(n).toString(16).padStart(2, '0')).join('');
}

function parseHex(hex: string): [number, number, number, number] {
  const bare = hex.replace('#', '');
  const wide = bare.length <= 4 ? bare.replace(/./g, (c) => c + c) : bare;
  const n = (i: number) => parseInt(wide.slice(i * 2, i * 2 + 2), 16);
  return [n(0), n(1), n(2), wide.length === 8 ? n(3) : 255];
}

/**
 * Resolve one custom-property value to RGBA.
 *
 * Three forms appear across the two stylesheets, and the third is why this
 * parses CSS rather than reading a table of hexes: the derived states are LIVE
 * blends (`color-mix`), so there is no hex anywhere to copy. Re-implementing
 * the blend is what keeps one source of truth instead of two.
 */
function resolveColor(
  value: string,
  all: Values,
  seen = new Set<string>(),
): [number, number, number, number] {
  const raw = value.trim();

  if (raw.startsWith('#')) return parseHex(raw);

  const rgb = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:\/\s*([\d.]+)\s*)?\)$/.exec(raw);
  if (rgb) {
    return [
      Number(rgb[1]),
      Number(rgb[2]),
      Number(rgb[3]),
      rgb[4] === undefined ? 255 : Number(rgb[4]) * 255,
    ];
  }

  // `color-mix(in srgb, var(--color-primary) 88%, black 12%)`. Mixed in
  // gamma-encoded sRGB, which is a plain weighted average of the 0-255 values —
  // NOT the linear-light average `srgb-linear` would give.
  const mix = /^color-mix\(\s*in\s+srgb\s*,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+?)\s+([\d.]+)%\s*\)$/.exec(raw);
  if (mix) {
    const a = resolveColor(mix[1] as string, all, seen);
    const b = resolveColor(mix[3] as string, all, seen);
    const wa = Number(mix[2]) / 100;
    const wb = Number(mix[4]) / 100;
    return [0, 1, 2, 3].map(
      (i) => (a[i] as number) * wa + (b[i] as number) * wb,
    ) as unknown as [number, number, number, number];
  }

  const varRef = /^var\(\s*(--[a-z0-9-]+)\s*\)$/.exec(raw);
  if (varRef) {
    const name = varRef[1] as string;
    if (seen.has(name)) throw new Error(`circular reference through ${name}`);
    const next = all[name];
    if (next === undefined) throw new Error(`${name} is referenced but never defined`);
    return resolveColor(next, all, new Set(seen).add(name));
  }

  if (raw === 'white') return [255, 255, 255, 255];
  if (raw === 'black') return [0, 0, 0, 255];
  if (raw === 'transparent') return [0, 0, 0, 0];

  throw new Error(`cannot resolve colour value "${raw}"`);
}

/**
 * Every `--*` declaration in a stylesheet's root token block.
 *
 * Two spellings, and both are load-bearing: the design system declares its
 * tokens in Tailwind v4's `@theme { … }` so they also become utility classes,
 * while `app.css` overrides them on plain `:root` — which is what the browser
 * cascade actually resolves against. Reading only one of the two silently
 * halves the palette.
 *
 * Blocks are read in source order and merged, so a file declaring both (or
 * declaring a token twice) ends with the same winner the browser would pick.
 */
function rootBlock(file: string): Values {
  const css = readFileSync(file, 'utf8');
  const blocks = [...css.matchAll(/(?:^|\n)(?::root|@theme)\s*\{([\s\S]*?)\n\}/g)];
  if (blocks.length === 0) {
    throw new Error(`${file}: no :root or @theme block — has the stylesheet been restructured?`);
  }
  const values: Values = {};
  for (const block of blocks) {
    for (const [, name, value] of (block[1] as string).matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
      values[name as string] = (value as string).trim();
    }
  }
  return values;
}

/**
 * The package's defaults with classroom's overrides on top — the same order the
 * browser resolves them in, since `app.css` imports `theme.css` and then
 * redeclares on `:root`.
 */
function tokens(): { colors: Values; radii: Values } {
  const merged: Values = { ...rootBlock(BASE_CSS), ...rootBlock(APP_CSS) };

  const colors: Values = {};
  const radii: Values = {};
  for (const [name, value] of Object.entries(merged)) {
    if (name.startsWith('--color-')) {
      colors[roleName(name, '--color-')] = cognitoColor(resolveColor(value, merged));
    } else if (name.startsWith('--radius-')) {
      const px = /^([\d.]+)px$/.exec(value.trim());
      if (px) radii[roleName(name, '--radius-')] = px[1] as string;
    }
  }
  return { colors, radii };
}

/** Walk a dotted path and assign. A missing path is a hard error, not a skip. */
function setAt(root: Record<string, unknown>, path: readonly string[], value: unknown): void {
  let node = root;
  for (const segment of path.slice(0, -1)) {
    const next = node[segment];
    if (next === undefined || typeof next !== 'object' || next === null) {
      throw new Error(`${OUT}: no such path segment "${segment}" in ${path.join('.')}`);
    }
    node = next as Record<string, unknown>;
  }
  const leaf = path[path.length - 1] as string;
  if (!(leaf in node)) throw new Error(`${OUT}: no such slot "${path.join('.')}"`);
  node[leaf] = value;
}

function reconcile(current: string): string {
  const { colors, radii } = tokens();
  const root = JSON.parse(current) as Record<string, unknown>;

  for (const [path, value] of STRUCTURE) setAt(root, path.split('.'), value);

  for (const [path, role] of RADII) {
    const value = radii[role];
    if (value === undefined) throw new Error(`no --radius-${role} resolves to a pixel value`);
    setAt(root, path.split('.'), Number(value));
  }

  // Classroom has ONE visual scheme, so both Cognito modes get the light
  // palette. A teacher whose laptop is in dark mode should not meet a dark
  // sign-in page in front of a light app.
  for (const mode of ['lightMode', 'darkMode']) {
    for (const [template, role] of SLOTS) {
      const value = colors[role];
      if (value === undefined) {
        throw new Error(`no --color-* property resolves to the role "${role}" named in SLOTS.`);
      }
      setAt(root, template.replace('{mode}', mode).split('.'), value);
    }
  }

  return `${JSON.stringify(root, null, 2)}\n`;
}

const current = readFileSync(OUT, 'utf8');
const reconciled = reconcile(current);

if (current === reconciled) {
  process.stdout.write('managed-login-settings.json is in sync with app.css.\n');
} else if (process.argv.includes('--check')) {
  process.stderr.write(
    'managed-login-settings.json has drifted from the stylesheets.\n\n' +
      'Either the file was hand-edited, or the brand changed without\n' +
      `regenerating. Run:\n\n  ${REGEN}\n`,
  );
  process.exitCode = 1;
} else {
  writeFileSync(OUT, reconciled);
  process.stdout.write('wrote managed-login-settings.json\n');
}

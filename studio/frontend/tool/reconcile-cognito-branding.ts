// Writes Studio's brand colours into the Cognito Managed Login style document.
//
// The sign-in, forced-new-password, reset and MFA pages are Cognito's, not
// ours — they cannot use `app.css`, only a colour document handed to AWS. This
// keeps that document in step with the stylesheet the app actually paints with,
// so the hosted page and the app cannot drift apart silently.
//
// `managed-login-settings.json` IS GENERATED — do not hand-edit it. JSON has no
// comment syntax and AWS rejects unknown keys, so the file cannot carry its own
// banner; this comment is it.
//
// Its STRUCTURE is AWS's schema, exported from the live branding record with
//   aws cognito-idp describe-managed-login-branding-by-client \
//     --user-pool-id <pool> --client-id <client> --return-merged-resources \
//     --query 'ManagedLoginBranding.Settings'
// To change layout, edit in the Cognito console's branding editor, re-export
// with that command, commit, then re-run `npm run brand` to put the token
// colours back over whatever the console wrote.
//
// STILL NO ASSETS, THOUGH THERE IS NOW A MARK. `src/utils/aperture.ts` draws
// studio's aperture and `tool/render-mark.ts` renders it to a file, so the
// artwork this comment used to say did not exist does. Uploading it is a
// separate job and is not done: `form.logo` stays disabled, no asset is
// declared, and Cognito keeps serving its own illustrations. When it is wired
// up it lands as an `asset` block in the Terraform — see humbugg's auth module
// for the shape.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
// The stylesheet IS the source of truth — there is no second copy of these
// values to keep in step. `index.html` pins `data-theme="dark"` and nothing
// toggles it, so that block is what actually paints.
const CSS = resolve(HERE, '../src/styles/app.css');
const OUT = resolve(HERE, '../../infra/modules/auth/managed-login-settings.json');
const REGEN = 'npm run brand';

type Colors = Record<string, string>;

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
  ['components.secondaryButton.{mode}.defaults.borderColor', 'primary'],
  ['components.secondaryButton.{mode}.defaults.textColor', 'primary'],
  ['components.secondaryButton.{mode}.hover.backgroundColor', 'surfaceAlt'],
  ['components.secondaryButton.{mode}.hover.borderColor', 'primaryHover'],
  ['components.secondaryButton.{mode}.hover.textColor', 'primaryHover'],
  ['components.secondaryButton.{mode}.active.backgroundColor', 'surfaceAlt'],
  ['components.secondaryButton.{mode}.active.borderColor', 'primaryActive'],
  ['components.secondaryButton.{mode}.active.textColor', 'primaryActive'],
  ['components.idpButton.standard.{mode}.defaults.backgroundColor', 'card'],
  ['components.idpButton.standard.{mode}.defaults.borderColor', 'line'],
  ['components.idpButton.standard.{mode}.defaults.textColor', 'ink'],
  ['components.idpButton.standard.{mode}.hover.backgroundColor', 'surfaceAlt'],
  ['components.idpButton.standard.{mode}.hover.borderColor', 'line'],
  ['components.idpButton.standard.{mode}.hover.textColor', 'ink'],
  ['components.idpButton.standard.{mode}.active.backgroundColor', 'surfaceAlt'],
  ['components.idpButton.standard.{mode}.active.borderColor', 'line'],
  ['components.idpButton.standard.{mode}.active.textColor', 'ink'],
  ['components.pageBackground.{mode}.color', 'bg'],
  ['components.form.{mode}.backgroundColor', 'card'],
  ['components.form.{mode}.borderColor', 'line'],
  ['components.pageFooter.{mode}.background.color', 'surfaceAlt'],
  ['components.pageFooter.{mode}.borderColor', 'line'],
  ['components.pageHeader.{mode}.background.color', 'surfaceAlt'],
  ['components.pageHeader.{mode}.borderColor', 'line'],
  ['components.pageText.{mode}.headingColor', 'ink'],
  ['components.pageText.{mode}.bodyColor', 'ink'],
  ['components.pageText.{mode}.descriptionColor', 'muted'],
  ['componentClasses.input.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.input.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.input.{mode}.placeholderColor', 'muted'],
  ['componentClasses.inputLabel.{mode}.textColor', 'ink'],
  ['componentClasses.inputDescription.{mode}.textColor', 'muted'],
  ['componentClasses.focusState.{mode}.borderColor', 'primary'],
  ['componentClasses.divider.{mode}.borderColor', 'line'],
  ['componentClasses.link.{mode}.defaults.textColor', 'primary'],
  ['componentClasses.link.{mode}.hover.textColor', 'primaryHover'],
  ['componentClasses.optionControls.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.optionControls.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.optionControls.{mode}.selected.backgroundColor', 'primary'],
  ['componentClasses.optionControls.{mode}.selected.foregroundColor', 'primaryText'],
  ['componentClasses.dropDown.{mode}.defaults.itemBackgroundColor', 'card'],
  ['componentClasses.dropDown.{mode}.hover.itemBackgroundColor', 'surfaceAlt'],
  ['componentClasses.dropDown.{mode}.hover.itemBorderColor', 'line'],
  ['componentClasses.dropDown.{mode}.hover.itemTextColor', 'ink'],
  ['componentClasses.dropDown.{mode}.match.itemTextColor', 'primary'],
  ['componentClasses.statusIndicator.{mode}.error.indicatorColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.error.borderColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.success.indicatorColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.success.borderColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.warning.indicatorColor', 'warning'],
  ['componentClasses.statusIndicator.{mode}.warning.borderColor', 'warning'],
  ['components.alert.{mode}.error.borderColor', 'danger'],
];

/**
 * Structural choices that are OURS, not AWS's defaults. All three default the
 * wrong way in a merged export and each is invisible until someone looks at the
 * page:
 *
 * - `colorSchemeMode` ships LIGHT. Studio is dark-only — `index.html` pins
 *   `data-theme="dark"` — so a LIGHT sign-in page would be a different product.
 * - `pageBackground.image.enabled` ships TRUE, and with no background asset of
 *   our own Cognito fills it with its own pastel gradient, which covers the
 *   brand background entirely.
 * - `form.logo.enabled` ships FALSE and stays false: Studio has no logo yet.
 *   Stated here rather than left to the default so that it reads as a decision.
 */
const STRUCTURE: ReadonlyArray<readonly [string, string | boolean]> = [
  ['categories.global.colorSchemeMode', 'DARK'],
  ['components.pageBackground.image.enabled', false],
  ['components.form.logo.enabled', false],
];

/** `--color-primary-text` → `primaryText`. */
function roleName(property: string): string {
  return property.replace(/^--color-/, '').replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
}

/** Cognito wants `rrggbbaa`, no leading `#`, lower-cased so diffs are stable. */
function cognitoColor(rgba: readonly [number, number, number, number]): string {
  return rgba.map((n) => Math.round(n).toString(16).padStart(2, '0')).join('');
}

function parseHex(hex: string): [number, number, number, number] {
  const bare = hex.replace('#', '');
  const n = (i: number) => parseInt(bare.slice(i * 2, i * 2 + 2), 16);
  return [n(0), n(1), n(2), bare.length === 8 ? n(3) : 255];
}

/**
 * Resolve one custom-property value to RGBA.
 *
 * Three forms appear in `app.css`, and the third is the reason this file parses
 * CSS rather than reading a table of hexes: the derived states are LIVE blends
 * (`color-mix`), so there is no hex anywhere to copy. Re-implementing the blend
 * is what keeps one source of truth instead of two.
 */
function resolve_(value: string, all: Record<string, string>, seen = new Set<string>()): [number, number, number, number] {
  const raw = value.trim();

  if (raw.startsWith('#')) return parseHex(raw);

  // `rgb(242 243 245 / 0.62)` — the space-separated form Tailwind v4 emits.
  const rgb = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:\/\s*([\d.]+)\s*)?\)$/.exec(raw);
  if (rgb) {
    return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3]), rgb[4] === undefined ? 255 : Number(rgb[4]) * 255];
  }

  // `color-mix(in srgb, var(--color-primary) 88%, white 12%)`. Mixed in
  // gamma-encoded sRGB, which is a plain weighted average of the 0-255 values —
  // NOT the linear-light average `srgb-linear` would give.
  const mix = /^color-mix\(\s*in\s+srgb\s*,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+?)\s+([\d.]+)%\s*\)$/.exec(raw);
  if (mix) {
    const a = resolve_(mix[1] as string, all, seen);
    const b = resolve_(mix[3] as string, all, seen);
    const wa = Number(mix[2]) / 100;
    const wb = Number(mix[4]) / 100;
    return [0, 1, 2, 3].map((i) => (a[i] as number) * wa + (b[i] as number) * wb) as unknown as [number, number, number, number];
  }

  const varRef = /^var\(\s*(--[a-z0-9-]+)\s*\)$/.exec(raw);
  if (varRef) {
    const name = varRef[1] as string;
    if (seen.has(name)) throw new Error(`${CSS}: circular reference through ${name}`);
    const next = all[name];
    if (next === undefined) throw new Error(`${CSS}: ${name} is referenced but never defined`);
    return resolve_(next, all, new Set(seen).add(name));
  }

  if (raw === 'white') return [255, 255, 255, 255];
  if (raw === 'black') return [0, 0, 0, 255];

  throw new Error(`${CSS}: cannot resolve colour value "${raw}"`);
}

/** The `[data-theme='dark']` block's custom properties, resolved to rrggbbaa. */
function readColors(): Colors {
  const css = readFileSync(CSS, 'utf8');
  const block = /\[data-theme='dark'\]\s*\{([\s\S]*?)\n\}/.exec(css);
  if (!block) throw new Error(`${CSS}: no [data-theme='dark'] block — has the stylesheet been restructured?`);

  const raw: Record<string, string> = {};
  for (const [, name, value] of (block[1] as string).matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    raw[name as string] = (value as string).trim();
  }

  const colors: Colors = {};
  for (const [name, value] of Object.entries(raw)) {
    if (name.startsWith('--color-')) colors[roleName(name)] = cognitoColor(resolve_(value, raw));
  }
  return colors;
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

function reconcile(colors: Colors, current: string): string {
  const root = JSON.parse(current) as Record<string, unknown>;

  for (const [path, value] of STRUCTURE) setAt(root, path.split('.'), value);

  // Studio has ONE visual scheme, so both Cognito modes get the dark palette.
  // An OS-light visitor should not meet a sign-in page in a Studio that does
  // not exist. When Studio designs a light scheme, this loop is where it stops
  // being a copy.
  for (const mode of ['lightMode', 'darkMode']) {
    for (const [template, role] of SLOTS) {
      const value = colors[role];
      if (value === undefined) {
        throw new Error(`${CSS}: no --color-* property resolves to the role "${role}" named in SLOTS.`);
      }
      setAt(root, template.replace('{mode}', mode).split('.'), value);
    }
  }

  return `${JSON.stringify(root, null, 2)}\n`;
}

const current = readFileSync(OUT, 'utf8');
const reconciled = reconcile(readColors(), current);

if (current === reconciled) {
  process.stdout.write('managed-login-settings.json is in sync with app.css.\n');
} else if (process.argv.includes('--check')) {
  process.stderr.write(
    'managed-login-settings.json has drifted from app.css.\n\n' +
      'Either the file was hand-edited, or the brand colours changed without\n' +
      `regenerating. Run:\n\n  ${REGEN}\n`,
  );
  process.exitCode = 1;
} else {
  writeFileSync(OUT, reconciled);
  process.stdout.write('wrote managed-login-settings.json\n');
}

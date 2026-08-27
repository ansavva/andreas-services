// Writes Humbugg's brand colours into the Cognito Managed Login style document.
//
// The sign-in, sign-up, forgot-password and MFA pages are Cognito's, not ours —
// we cannot style them with the design system, only hand AWS a colour document.
// This keeps that document in step with `src/theme/brand-colors.json`, which is
// the same file the app's ThemeProvider reads, so the hosted page and the app
// cannot drift apart silently.
//
// `managed-login-settings.json` IS GENERATED — do not hand-edit it. JSON has no
// comment syntax and AWS rejects unknown keys, so the file cannot carry its own
// banner; this comment is it.
//
// Its STRUCTURE is AWS's schema, exported from the live branding record with
//   aws cognito-idp describe-managed-login-branding-by-client \
//     --user-pool-id <pool> --client-id <client> --return-merged-resources \
//     --query 'ManagedLoginBranding.Settings'
// To change layout — border radii, which auth methods show, spacing — edit in
// the Cognito console's branding editor, re-export with that command, commit,
// then re-run `npm run brand` to put the token colours back over whatever the
// console wrote.
//
// COLOURS ONLY, NO ASSETS, deliberately. Humbugg has no wordmark sized for this
// page, and a merged export folds in Cognito's own illustrations — committing
// those would be checking in someone else's artwork. Undeclared assets are left
// alone, so Cognito keeps serving its defaults. A real logo lands here later as
// `asset` blocks (filebase64, <= 40 assets, 2 MB each).
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const BRAND = resolve(HERE, '../src/theme/brand-colors.json');
const PACKAGE_COLORS = resolve(HERE, '../node_modules/@ansavva/tokens/src/colors.json');
const OUT = resolve(HERE, '../../infra/modules/auth/managed-login-settings.json');
const REGEN = 'npm run brand';

type Colors = Record<string, string>;

/**
 * Which Cognito colour slot each semantic role fills. `{mode}` is substituted
 * with `lightMode` and `darkMode`.
 *
 * Semantic roles only — never raw palette names. The design system exports no
 * palette names in either direction, on purpose: overriding roles is what keeps
 * a re-brand a one-place change.
 */
const SLOTS: ReadonlyArray<readonly [string, string]> = [
  // The "Sign in" call to action.
  ['components.primaryButton.{mode}.defaults.backgroundColor', 'primary'],
  ['components.primaryButton.{mode}.defaults.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.hover.backgroundColor', 'primaryHover'],
  ['components.primaryButton.{mode}.hover.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.active.backgroundColor', 'primaryActive'],
  ['components.primaryButton.{mode}.active.textColor', 'primaryText'],
  ['components.primaryButton.{mode}.disabled.backgroundColor', 'muted'],
  ['components.primaryButton.{mode}.disabled.borderColor', 'muted'],
  // Secondary actions and the federated-provider buttons.
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
  // Page and form surfaces.
  ['components.pageBackground.{mode}.color', 'bg'],
  ['components.form.{mode}.backgroundColor', 'card'],
  ['components.form.{mode}.borderColor', 'line'],
  ['components.pageFooter.{mode}.background.color', 'surfaceAlt'],
  ['components.pageFooter.{mode}.borderColor', 'line'],
  ['components.pageHeader.{mode}.background.color', 'surfaceAlt'],
  ['components.pageHeader.{mode}.borderColor', 'line'],
  // Text.
  ['components.pageText.{mode}.headingColor', 'ink'],
  ['components.pageText.{mode}.bodyColor', 'ink'],
  ['components.pageText.{mode}.descriptionColor', 'muted'],
  // Inputs, labels, the focus ring.
  ['componentClasses.input.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.input.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.input.{mode}.placeholderColor', 'muted'],
  ['componentClasses.inputLabel.{mode}.textColor', 'ink'],
  ['componentClasses.inputDescription.{mode}.textColor', 'muted'],
  ['componentClasses.focusState.{mode}.borderColor', 'primary'],
  ['componentClasses.divider.{mode}.borderColor', 'line'],
  // Links — "Forgot your password?" is the one every visitor sees.
  ['componentClasses.link.{mode}.defaults.textColor', 'primary'],
  ['componentClasses.link.{mode}.hover.textColor', 'primaryHover'],
  // Selection controls and the country dropdown.
  ['componentClasses.optionControls.{mode}.defaults.backgroundColor', 'card'],
  ['componentClasses.optionControls.{mode}.defaults.borderColor', 'line'],
  ['componentClasses.optionControls.{mode}.selected.backgroundColor', 'primary'],
  ['componentClasses.optionControls.{mode}.selected.foregroundColor', 'primaryText'],
  ['componentClasses.dropDown.{mode}.defaults.itemBackgroundColor', 'card'],
  ['componentClasses.dropDown.{mode}.hover.itemBackgroundColor', 'surfaceAlt'],
  ['componentClasses.dropDown.{mode}.hover.itemBorderColor', 'line'],
  ['componentClasses.dropDown.{mode}.hover.itemTextColor', 'ink'],
  ['componentClasses.dropDown.{mode}.match.itemTextColor', 'primary'],
  // Status.
  ['componentClasses.statusIndicator.{mode}.error.indicatorColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.error.borderColor', 'danger'],
  ['componentClasses.statusIndicator.{mode}.success.indicatorColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.success.borderColor', 'success'],
  ['componentClasses.statusIndicator.{mode}.warning.indicatorColor', 'warning'],
  ['componentClasses.statusIndicator.{mode}.warning.borderColor', 'warning'],
  ['components.alert.{mode}.error.borderColor', 'danger'],
];

/**
 * The structural choices that are OURS rather than AWS's defaults.
 *
 * Everything else in the document is layout the console editor owns, but these
 * two decide whether the page looks like Humbugg at all, and both default the
 * wrong way in a merged export:
 *
 * - `pageBackground.image.enabled` ships TRUE, and with no PAGE_BACKGROUND
 *   asset of our own Cognito fills it with its own pastel gradient — which is
 *   what covered the brand background on the first branded deploy. The page
 *   background colour below only shows once this is off.
 * - `form.logo.enabled` ships FALSE, so the FORM_LOGO asset the Terraform
 *   uploads would be ignored.
 *
 * They are set here, not hand-edited into the JSON, so that a re-export from
 * the console cannot quietly restore AWS's defaults.
 */
const STRUCTURE: ReadonlyArray<readonly [string, boolean]> = [
  ['components.pageBackground.image.enabled', false],
  ['components.form.logo.enabled', true],
];

/** Cognito wants `rrggbbaa`, no leading `#`, lower-cased so diffs are stable. */
function cognitoColor(hex: string): string {
  const bare = hex.replace('#', '').toLowerCase();
  return bare.length === 8 ? bare : `${bare}ff`;
}

/**
 * Walk a dotted path and assign. A path that does not exist is a hard error,
 * not a skip: a console re-export that drops a component would otherwise
 * silently leave AWS's blue behind in a slot nobody is watching.
 */
function setColor(root: Record<string, unknown>, path: readonly string[], value: string): void {
  let node = root;
  for (const segment of path.slice(0, -1)) {
    const next = node[segment];
    if (next === undefined || typeof next !== 'object' || next === null) {
      throw new Error(`${OUT}: no such path segment "${segment}" in ${path.join('.')}`);
    }
    node = next as Record<string, unknown>;
  }
  const leaf = path[path.length - 1] as string;
  if (!(leaf in node)) throw new Error(`${OUT}: no such colour slot "${path.join('.')}"`);
  node[leaf] = value;
}

/** Same walk as `setColor`, for the boolean structure above. */
function setFlag(root: Record<string, unknown>, path: readonly string[], value: boolean): void {
  let node = root;
  for (const segment of path.slice(0, -1)) {
    const next = node[segment];
    if (next === undefined || typeof next !== 'object' || next === null) {
      throw new Error(`${OUT}: no such path segment "${segment}" in ${path.join('.')}`);
    }
    node = next as Record<string, unknown>;
  }
  const leaf = path[path.length - 1] as string;
  if (!(leaf in node)) throw new Error(`${OUT}: no such flag "${path.join('.')}"`);
  node[leaf] = value;
}

function reconcile(colors: Colors, current: string): string {
  const root = JSON.parse(current) as Record<string, unknown>;

  for (const [path, value] of STRUCTURE) setFlag(root, path.split('.'), value);

  // Humbugg has ONE visual scheme. `theme.ts` pins the app to it by resolving
  // `dark` to the light values, and the same reasoning applies here: an OS-dark
  // visitor should not meet a sign-in page in a brand that is not Humbugg. Both
  // Cognito modes therefore get the same colours. When Humbugg designs a dark
  // scheme, this loop is where it stops being a copy.
  for (const mode of ['lightMode', 'darkMode']) {
    for (const [template, role] of SLOTS) {
      const hex = colors[role];
      if (hex === undefined) {
        throw new Error(
          `no such semantic role "${role}" — brand-colors.json and the tokens ` +
            'package between them must supply every role named in SLOTS.',
        );
      }
      setColor(root, template.replace('{mode}', mode).split('.'), cognitoColor(hex));
    }
  }

  return `${JSON.stringify(root, null, 2)}\n`;
}

const brand = JSON.parse(readFileSync(BRAND, 'utf8')) as Colors;
// The roles Humbugg does not override — success, warning, danger — come from
// the package, exactly as the app reads them through `var(--color-danger)`.
const packaged = (JSON.parse(readFileSync(PACKAGE_COLORS, 'utf8')) as { light: Colors }).light;
const colors: Colors = { ...packaged, ...brand };

const current = readFileSync(OUT, 'utf8');
const reconciled = reconcile(colors, current);

if (current === reconciled) {
  process.stdout.write('managed-login-settings.json is in sync with brand-colors.json.\n');
} else if (process.argv.includes('--check')) {
  process.stderr.write(
    'managed-login-settings.json has drifted from brand-colors.json.\n\n' +
      'Either the file was hand-edited, or the brand colours changed without\n' +
      `regenerating. Run:\n\n  ${REGEN}\n`,
  );
  process.exitCode = 1;
} else {
  writeFileSync(OUT, reconciled);
  process.stdout.write('wrote managed-login-settings.json\n');
}

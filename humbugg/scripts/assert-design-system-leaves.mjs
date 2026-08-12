#!/usr/bin/env node
// Assert that a build resolved the design system's intended platform leaf.
//
// @ansavva/design-system ships every component as a `.web.tsx` / `.native.tsx`
// pair behind one extensionless re-export, and the CONSUMER'S BUNDLER picks the
// leaf. Resolving the wrong one compiles cleanly, bundles cleanly, and passes
// every type check and unit test — it only shows up as a screen that renders
// wrong, which is exactly the class of failure CI otherwise cannot see.
//
//   humbugg/marketing  (Vite)   must take .web.tsx   — Tailwind classes over theme.css
//   humbugg/app  (Metro)  must take .native.tsx — RN primitives over the tokens,
//                                                 rendered by react-native-web
//
// Metro is the one that gets this wrong unaided: for `platform: 'web'` its
// candidate extensions are `.web.tsx` then `.tsx`, and `.native` is not
// considered at all. humbugg/app/metro.config.js corrects it; this script is
// what proves the correction is still working.
//
// Usage:
//   node humbugg/scripts/assert-design-system-leaves.mjs native humbugg/app/dist
//   node humbugg/scripts/assert-design-system-leaves.mjs web   humbugg/marketing/build
//
// The native mode reads source maps, which is the only trustworthy signal.
// Grepping the bundle for "react-native-web" is NOT equivalent and must not be
// substituted: react-native-web is present in any Expo web build because the
// app's own primitives use it, so the grep passes whichever leaf was resolved.
// It answers "is this an Expo web build", not "did the design system resolve
// native leaves". Build with `--source-maps` for this to work.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const PACKAGE = '@ansavva/design-system';

const [mode, root] = process.argv.slice(2);
if (mode !== 'native' && mode !== 'web') {
  console.error('usage: assert-design-system-leaves.mjs <native|web> <build-dir>');
  process.exit(2);
}

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

let files;
try {
  files = walk(root);
} catch {
  console.error(`✗ ${root} does not exist — build first.`);
  process.exit(1);
}

const counts = { native: 0, web: 0 };
const seen = { native: new Set(), web: new Set() };

if (mode === 'native') {
  const maps = files.filter((f) => f.endsWith('.map'));
  if (maps.length === 0) {
    console.error(`✗ no source maps under ${root}. Export with --source-maps.`);
    process.exit(1);
  }
  for (const map of maps) {
    let sources;
    try {
      sources = JSON.parse(readFileSync(map, 'utf8')).sources ?? [];
    } catch {
      continue;
    }
    for (const source of sources) {
      if (!source.includes(PACKAGE)) continue;
      if (source.endsWith('.native.tsx')) { counts.native++; seen.native.add(source); }
      else if (source.endsWith('.web.tsx')) { counts.web++; seen.web.add(source); }
    }
  }
} else {
  // A web build has no business shipping the React Native renderer. Unlike the
  // native direction, this negative check IS meaningful: nothing in a Vite web
  // app pulls react-native-web in unless a .native leaf was resolved.
  const offenders = files.filter(
    (f) => /\.(js|mjs|css)$/.test(f) && readFileSync(f, 'utf8').includes('react-native-web'),
  );
  if (offenders.length > 0) {
    console.error('✗ react-native-web reached the web bundle — a .native leaf was resolved:');
    for (const f of offenders.slice(0, 5)) console.error(`    ${f}`);
    process.exit(1);
  }

  // The positive signal is in the CSS, not the filenames: this build inlines the
  // package rather than emitting a chunk per component, so there is no
  // `button.web-<hash>.js` to look for. But only the WEB leaves carry Tailwind
  // class strings, and those classes only reach the stylesheet if Tailwind also
  // scanned the package (the `@source` directive). One check, both facts —
  // absence means either the wrong leaf or unstyled components.
  const MARKERS = ['bg-primary', 'text-primary-text', 'bg-primary-hover', 'bg-primary-active'];
  const css = files.filter((f) => f.endsWith('.css'));
  for (const file of css) {
    const text = readFileSync(file, 'utf8');
    const hits = MARKERS.filter((m) => text.includes(m));
    if (hits.length === MARKERS.length) { counts.web++; seen.web.add(file); }
  }
  if (counts.web === 0) {
    console.error(
      `✗ no stylesheet under ${root} carries the design system's own variant classes ` +
        `(${MARKERS.join(', ')}).\n` +
        '  Either a .native leaf was resolved, or Tailwind never scanned the package — ' +
        'check the @source directive in the CSS entrypoint. Components would render unstyled.',
    );
    process.exit(1);
  }
  console.log(`✓ no react-native-web, and ${counts.web} stylesheet(s) carry the web leaves' classes.`);
  process.exit(0);
}

const wanted = mode;
const unwanted = mode === 'native' ? 'web' : 'native';

if (counts[unwanted] > 0) {
  console.error(
    `✗ expected only .${wanted} leaves, found ${counts[unwanted]} .${unwanted} reference(s):`,
  );
  for (const s of [...seen[unwanted]].slice(0, 5)) console.error(`    ${s}`);
  process.exit(1);
}

if (counts[wanted] === 0) {
  console.error(
    `✗ found no .${wanted} leaves at all under ${root}. Either the design system is not ` +
      'bundled, or the build shape changed and this check is now blind — investigate rather ' +
      'than relaxing it.',
  );
  process.exit(1);
}

console.log(`✓ ${counts[wanted]} .${wanted} leaves, 0 .${unwanted} — correct leaf resolved.`);

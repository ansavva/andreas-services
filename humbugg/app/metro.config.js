// Metro configuration.
//
// ── Why this file exists at all ──────────────────────────────────────────────
//
// `@ansavva/design-system` ships every component as a `.web.tsx` / `.native.tsx`
// pair behind one extensionless re-export, and the consumer's bundler picks the
// leaf. Three consumers, three answers:
//
//   Vite web app            → .web.tsx    (Tailwind classes over theme.css)
//   React Native app        → .native.tsx (RN primitives over the tokens)
//   React Native app ON WEB → .native.tsx (react-native-web renders the RN tree)
//
// This app is the third row, and it is the row Metro gets wrong on its own.
// For `platform: 'web'` Metro's candidate extensions are `.web.tsx` then `.tsx`
// — `.native` is not even considered — so an unconfigured web export silently
// takes the WEB leaves. They compile, they bundle, and they render completely
// unstyled, because a Tailwind class string means nothing to a project with no
// Tailwind pipeline. Nothing fails; the app just stops looking like Humbugg.
//
// ── What the fix does ────────────────────────────────────────────────────────
//
// For a relative import made FROM INSIDE the design system while building for
// web, try the same specifier with `.native` appended first, and fall back to
// normal resolution when there is no such file. That is narrow on purpose:
//
//   • Only intra-package requests are touched, so the app's own `.web` files
//     (if it ever grows any) still win normally.
//   • Only RELATIVE specifiers are touched. Bare ones are left alone, which
//     matters most for `react-native` itself: Expo's web config aliases it to
//     `react-native-web`, and that alias is keyed off the platform. Rewriting
//     the platform instead of the path would resolve the real native renderer
//     into a browser bundle.
//   • The fallback is what makes it safe on directory re-exports
//     (`./accordion` → `accordion/index.ts`) and on shared modules with no
//     leaf pair (`./button.props`), neither of which has a `.native` file.
//
// Verify it with a source map: `npx expo export -p web --source-maps` and check
// that the design-system sources are `*.native.tsx`. `.web.tsx` in that list
// means this resolver stopped working.
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const config = getDefaultConfig(__dirname);

const DESIGN_SYSTEM_DIR = `${path.sep}${path.join('@ansavva', 'design-system')}${path.sep}`;

const upstreamResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  const resolve = upstreamResolveRequest ?? context.resolveRequest;
  const fromDesignSystem = context.originModulePath?.includes(DESIGN_SYSTEM_DIR) ?? false;

  if (platform === 'web' && fromDesignSystem && moduleName.startsWith('.')) {
    try {
      return resolve(context, `${moduleName}.native`, platform);
    } catch {
      // No `.native` leaf for this specifier — a directory index or a shared
      // props module. Fall through to what Metro would have done anyway.
    }
  }

  return resolve(context, moduleName, platform);
};

module.exports = config;

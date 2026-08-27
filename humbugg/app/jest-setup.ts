// Shared test setup for `jest-expo`.
//
// Everything here mocks a NATIVE module the screens reach for. None of them has
// a JS implementation under jest, so without a mock the import itself throws
// before a single assertion runs.
// (`@testing-library/react-native` ships its matchers by default since v12.4,
// so there is no `extend-expect` entry point to import.)

// Metro inlines EXPO_PUBLIC_* at build time; under jest they are ordinary
// environment variables, read once when a module is imported. This file runs
// before the test module does, which is the only window to set them. Fixtures —
// nothing here reaches a real pool.
process.env.EXPO_PUBLIC_COGNITO_DOMAIN ??= 'auth.humbugg.test';
process.env.EXPO_PUBLIC_COGNITO_CLIENT_ID ??= 'test-client-id';

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() },
}));

// The keychain behind the OAuth token store.
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-web-browser', () => ({
  openAuthSessionAsync: jest.fn().mockResolvedValue({ type: 'dismiss' }),
  maybeCompleteAuthSession: jest.fn(),
}));

jest.mock('expo-image-picker', () => ({
  launchImageLibraryAsync: jest.fn().mockResolvedValue({ canceled: true, assets: null }),
}));

jest.mock('expo-clipboard', () => ({ setStringAsync: jest.fn().mockResolvedValue(true) }));

jest.mock('expo-linking', () => ({
  getInitialURL: jest.fn().mockResolvedValue(null),
  createURL: (path: string) => `humbugg://${path}`,
}));

// `useFonts` resolves immediately so the root layout is never in its loading
// branch during a test. Tests render screens directly, but this keeps the mock
// available for anything that mounts the layout.
jest.mock('expo-font', () => ({
  useFonts: () => [true, null],
  isLoaded: () => true,
}));

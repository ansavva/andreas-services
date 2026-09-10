// The one decision the whole app's colour hangs off: what scheme is painted.
//
// The overriding pair are the tests that could not have passed before
// design-system 0.22.0 — a stored `dark` has to beat a light device, not merge
// with it. The sheet assertion is here rather than in a `styles.test.ts` because
// it is the same claim from the other end: whatever this provider resolves, the
// hand-written sheets follow it, and the two halves of a screen cannot disagree.
// The last test pins the fallback the existing suite leans on: a screen rendered
// on its own, with no provider above it, still follows the device.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Appearance, Text } from 'react-native';

import { THEME_KEY } from '../utils/theme-preference';

import { SchemePreferenceProvider, useSchemePreference } from './scheme-preference';
import { useTheme } from './styles';
import { palettes } from './theme';

/** The mock `jest-setup.ts` installs; typed here so the assertions can read it. */
const storage = AsyncStorage as unknown as {
  getItem: jest.Mock;
  setItem: jest.Mock;
  removeItem: jest.Mock;
};

// The device, mocked at the seam the provider actually reads — `Appearance`,
// not `useColorScheme`. `listeners` is what lets a test change the device's mind
// after the app has started, which is the only way to prove "System follows it".
type AppearanceListener = Parameters<typeof Appearance.addChangeListener>[0];
const listeners: AppearanceListener[] = [];

jest.spyOn(Appearance, 'getColorScheme').mockImplementation(() => 'light');
jest.spyOn(Appearance, 'addChangeListener').mockImplementation((listener) => {
  listeners.push(listener);
  return {
    remove: () => {
      const at = listeners.indexOf(listener);
      if (at >= 0) listeners.splice(at, 1);
    },
  };
});

/** What the device says now, and what it says from here on. */
function setDeviceScheme(scheme: 'light' | 'dark'): void {
  (Appearance.getColorScheme as jest.Mock).mockReturnValue(scheme);
}

function Probe() {
  const { preference, resolved, setPreference } = useSchemePreference();
  const { brand } = useTheme();
  return (
    <>
      <Text>{`preference: ${preference}`}</Text>
      <Text>{`resolved: ${resolved}`}</Text>
      <Text>{`bg: ${brand.bg}`}</Text>
      <Text testID="set-dark" onPress={() => setPreference('dark')}>
        dark
      </Text>
      <Text testID="set-system" onPress={() => setPreference('system')}>
        system
      </Text>
    </>
  );
}

function renderProbe() {
  return render(
    <SchemePreferenceProvider>
      <Probe />
    </SchemePreferenceProvider>,
  );
}

describe('SchemePreferenceProvider', () => {
  beforeEach(() => {
    storage.getItem.mockReset().mockResolvedValue(null);
    storage.setItem.mockReset().mockResolvedValue(undefined);
    storage.removeItem.mockReset().mockResolvedValue(undefined);
    setDeviceScheme('light');
    listeners.length = 0;
  });

  it('follows the device when nothing is stored', async () => {
    setDeviceScheme('dark');
    renderProbe();

    expect(await screen.findByText('preference: system')).toBeTruthy();
    expect(screen.getByText('resolved: dark')).toBeTruthy();
  });

  /**
   * The device changes its mind while the app is open, and the app follows.
   *
   * Worth a test of its own because the obvious implementation fails it: React
   * Native Web's `useColorScheme()` re-subscribes on every render, and the
   * provider's subscription — added last, dispatched last — was torn down
   * mid-dispatch by the re-renders the earlier subscribers caused. The app then
   * followed the device until the first repaint and never again. Subscribing
   * once is what this asserts.
   */
  it('keeps following the device after the app has started', async () => {
    setDeviceScheme('light');
    renderProbe();
    expect(await screen.findByText('resolved: light')).toBeTruthy();

    setDeviceScheme('dark');
    act(() => {
      for (const listener of [...listeners]) listener({ colorScheme: 'dark' });
    });

    expect(screen.getByText('resolved: dark')).toBeTruthy();
    expect(screen.getByText(`bg: ${palettes.dark.bg}`)).toBeTruthy();
  });

  it('a forced scheme ignores the device changing its mind', async () => {
    setDeviceScheme('light');
    storage.getItem.mockResolvedValue('light');
    renderProbe();
    expect(await screen.findByText('resolved: light')).toBeTruthy();

    setDeviceScheme('dark');
    act(() => {
      for (const listener of [...listeners]) listener({ colorScheme: 'dark' });
    });

    expect(screen.getByText('resolved: light')).toBeTruthy();
  });

  it('paints nothing until the stored preference has been read', () => {
    // Never resolves — the gate, held open.
    storage.getItem.mockReturnValue(new Promise(() => {}));
    renderProbe();

    expect(screen.queryByText(/^preference:/)).toBeNull();
  });

  it('a stored dark overrides a light device', async () => {
    setDeviceScheme('light');
    storage.getItem.mockResolvedValue('dark');
    renderProbe();

    expect(await screen.findByText('preference: dark')).toBeTruthy();
    expect(screen.getByText('resolved: dark')).toBeTruthy();
  });

  it('a stored light overrides a dark device', async () => {
    setDeviceScheme('dark');
    storage.getItem.mockResolvedValue('light');
    renderProbe();

    expect(await screen.findByText('preference: light')).toBeTruthy();
    expect(screen.getByText('resolved: light')).toBeTruthy();
  });

  it('an unrecognised stored value is no preference at all', async () => {
    setDeviceScheme('light');
    storage.getItem.mockResolvedValue('sepia');
    renderProbe();

    expect(await screen.findByText('preference: system')).toBeTruthy();
    expect(screen.getByText('resolved: light')).toBeTruthy();
  });

  it('writes the key for a scheme and removes it for system', async () => {
    renderProbe();
    const dark = await screen.findByTestId('set-dark');

    fireEvent.press(dark);
    await waitFor(() => expect(storage.setItem).toHaveBeenCalledWith(THEME_KEY, 'dark'));
    expect(await screen.findByText('resolved: dark')).toBeTruthy();

    fireEvent.press(screen.getByTestId('set-system'));
    await waitFor(() => expect(storage.removeItem).toHaveBeenCalledWith(THEME_KEY));
    // `system` is the absence of a row, never the string "system".
    expect(storage.setItem).not.toHaveBeenCalledWith(THEME_KEY, 'system');
  });

  it("the app's own sheets follow a forced scheme, not the device", async () => {
    setDeviceScheme('light');
    storage.getItem.mockResolvedValue('dark');
    renderProbe();

    expect(await screen.findByText(`bg: ${palettes.dark.bg}`)).toBeTruthy();
    expect(palettes.dark.bg).not.toBe(palettes.light.bg);
  });

  it('resolves to the device outside a provider, as every screen did before the switch', () => {
    setDeviceScheme('dark');
    render(<Probe />);

    expect(screen.getByText('preference: system')).toBeTruthy();
    expect(screen.getByText('resolved: dark')).toBeTruthy();
    expect(screen.getByText(`bg: ${palettes.dark.bg}`)).toBeTruthy();
  });
});

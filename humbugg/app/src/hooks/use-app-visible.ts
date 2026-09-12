// Whether the app is in front of the person right now.
//
// `AppState` is the one seam that answers on every platform: the OS's foreground state on a
// device, `document.visibilityState` through react-native-web in a browser. The chat polls slower
// while nobody is looking, and refetches the moment somebody is again.
import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

export function useAppVisible(): boolean {
  const [visible, setVisible] = useState(AppState.currentState !== 'background' && AppState.currentState !== 'inactive');
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => setVisible(state === 'active'));
    return () => subscription.remove();
  }, []);
  return visible;
}

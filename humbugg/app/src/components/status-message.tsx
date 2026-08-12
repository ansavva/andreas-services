// `.status-message` / `.status-error` / `.status-success` from the web app.
//
// Deliberately NOT the design system's `Alert`: that draws a coloured stripe,
// an icon slot and a title/description pair, which is a different component from
// the flat tinted bar Humbugg shows under a form. Composing `Alert` down to this
// would mean overriding more of it than it leaves alone. What is kept from it is
// the accessibility contract — `role="status"`, matching the web app.
import { Text, View } from 'react-native';

import { styles } from '../theme/styles';

export function StatusMessage({
  message,
  tone = 'error',
}: {
  message?: string | null;
  tone?: 'error' | 'success';
}) {
  if (!message) return null;
  const success = tone === 'success';
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.statusMessage, success ? styles.statusSuccess : styles.statusError]}
    >
      <Text style={[styles.statusMessageText, success ? styles.statusSuccessText : styles.statusErrorText]}>
        {message}
      </Text>
    </View>
  );
}

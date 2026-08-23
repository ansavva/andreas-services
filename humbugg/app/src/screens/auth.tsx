// Sign in / sign up / confirm / reset, ported from `src/pages/AuthPage.tsx`.
//
// One screen behind four routes, exactly as before — the flows share a form and
// differ only in which fields show and what submit does. `mode` now arrives from
// the route file rather than from a React Router route element.
import { Button, Checkbox, Input } from '@ansavva/design-system';
import { Link, useRouter } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, Shell } from '../components/shell';
import { FieldLabel } from '../components/field';
import { StatusMessage } from '../components/status-message';
import { recordPolicyConsent } from '../config/policies';
import { webUrl } from '../config/site';
import { useAuth } from '../context/auth-context';
import { gap, styles } from '../theme/styles';
import { sessionKeys, sessionStore } from '../utils/session-store';
import { validatePassword } from '../utils/validation';

export type AuthMode = 'login' | 'signup' | 'confirm' | 'forgot';

export default function AuthScreen({ mode }: { mode: AuthMode }) {
  const auth = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState(() => sessionStore.get(sessionKeys.email) ?? '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [code, setCode] = useState('');
  const [stage, setStage] = useState<'request' | 'confirm'>('request');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // Explicit, unchecked-by-default agreement to the Terms and Privacy Policy; gates account creation.
  const [consented, setConsented] = useState(false);

  const title =
    mode === 'login'
      ? 'Welcome back'
      : mode === 'signup'
        ? 'Create your Humbugg account'
        : mode === 'confirm'
          ? 'Check your email'
          : 'Reset your password';

  async function submit() {
    setBusy(true);
    setMessage(null);
    try {
      if (mode === 'login') {
        await auth.login(email.trim(), password);
        const returnTo = sessionStore.get(sessionKeys.returnTo);
        const needsProfileSetup = sessionStore.get(sessionKeys.consent) !== null;
        sessionStore.remove(sessionKeys.returnTo);
        router.replace(needsProfileSetup ? '/' : ((returnTo ?? '/') as '/'));
      } else if (mode === 'signup') {
        const passwordError = validatePassword(password);
        if (passwordError) { setMessage(passwordError); return; }
        if (password !== confirmPassword) { setMessage('Passwords must match.'); return; }
        if (!consented) { setMessage('Please agree to the Terms of Service and Privacy Policy to create your account.'); return; }
        // Capture the consent (policy version + UTC timestamp) at the moment of agreement, stash it so it
        // survives the confirm → sign-in → profile-setup flow, and record it when the profile is created.
        const consent = recordPolicyConsent();
        const normalizedEmail = email.trim();
        await auth.register(normalizedEmail, password);
        sessionStore.set(sessionKeys.email, normalizedEmail);
        sessionStore.set(sessionKeys.consent, JSON.stringify(consent));
        router.push('/confirm');
      } else if (mode === 'confirm') {
        await auth.confirm(email.trim(), code.trim());
        setMessage('Your email is confirmed. You can sign in now.');
      } else if (stage === 'request') {
        const normalizedEmail = email.trim();
        await auth.beginReset(normalizedEmail);
        sessionStore.set(sessionKeys.email, normalizedEmail);
        setStage('confirm');
        setMessage('We sent a reset code to your email.');
      } else {
        const passwordError = validatePassword(password);
        if (passwordError) { setMessage(passwordError); return; }
        await auth.finishReset(email.trim(), code.trim(), password);
        setMessage('Password updated. You can sign in now.');
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  const needsCode = mode === 'confirm' || (mode === 'forgot' && stage === 'confirm');
  const needsPassword = mode === 'login' || mode === 'signup' || (mode === 'forgot' && stage === 'confirm');
  const submitLabel = busy
    ? 'Please wait…'
    : mode === 'login'
      ? 'Sign in'
      : mode === 'signup'
        ? 'Create account'
        : mode === 'confirm'
          ? 'Confirm email'
          : stage === 'request'
            ? 'Send reset code'
            : 'Update password';

  return (
    <Shell>
      <View style={{ gap: 40, paddingVertical: 32 }}>
        <View style={local.pitch}>
          <Text style={styles.eyebrow}>A calmer way to coordinate</Text>
          <Text style={[styles.displayXl, { marginTop: 16 }]}>The magic stays secret.{'\n'}The planning stays simple.</Text>
          <Text style={[styles.bodyMuted, { marginTop: 20, maxWidth: 448 }]}>
            One account keeps your groups, wish lists, and private assignments together.
          </Text>
        </View>
        <Card roomy style={local.card}>
          <Text style={styles.displayMd}>{title}</Text>
          <Text style={[styles.bodyMuted, { marginTop: 8 }]}>
            {mode === 'confirm'
              ? 'Enter the six-digit confirmation code we sent you.'
              : 'Use your email address to continue.'}
          </Text>
          <View style={{ marginTop: 28, gap: gap.lg }}>
            <FieldLabel label="Email address">
              <Input
                type="email"
                aria-label="Email address"
                textContentType="emailAddress"
                maxLength={254}
                value={email}
                onValueChange={setEmail}
              />
            </FieldLabel>
            {needsCode ? (
              <FieldLabel label="Confirmation code">
                <Input
                  type="tel"
                  aria-label="Confirmation code"
                  textContentType="oneTimeCode"
                  maxLength={6}
                  value={code}
                  onValueChange={setCode}
                />
              </FieldLabel>
            ) : null}
            {needsPassword ? (
              <PasswordField
                label={mode === 'forgot' ? 'New password' : 'Password'}
                value={password}
                onChange={setPassword}
                visible={showPassword}
                onToggleVisibility={() => setShowPassword((visible) => !visible)}
                enforcePolicy={mode !== 'login'}
              />
            ) : null}
            {mode === 'signup' ? (
              <PasswordField
                label="Confirm password"
                value={confirmPassword}
                onChange={setConfirmPassword}
                visible={showConfirmPassword}
                onToggleVisibility={() => setShowConfirmPassword((visible) => !visible)}
                enforcePolicy
              />
            ) : null}
            {mode === 'signup' ? (
              <View style={local.consentRow}>
                <Checkbox.Root
                  checked={consented}
                  onCheckedChange={(checked) => setConsented(checked === true)}
                  aria-label="Agree to the Terms of Service and Privacy Policy"
                >
                  <Checkbox.Indicator />
                </Checkbox.Root>
                <Text style={[styles.smallMuted, { flex: 1 }]}>
                  I agree to Humbugg&apos;s{' '}
                  <Text style={styles.link} onPress={() => void Linking.openURL(webUrl('/terms'))}>
                    Terms of Service
                  </Text>{' '}
                  and{' '}
                  <Text style={styles.link} onPress={() => void Linking.openURL(webUrl('/privacy'))}>
                    Privacy Policy
                  </Text>
                  .
                </Text>
              </View>
            ) : null}
            <StatusMessage
              message={message}
              tone={
                message?.includes('confirmed') || message?.includes('updated') || message?.includes('sent')
                  ? 'success'
                  : 'error'
              }
            />
            <Button size="lg" disabled={busy} onPress={() => void submit()}>
              {submitLabel}
            </Button>
          </View>
          <View style={local.switcher}>
            {mode !== 'login' ? (
              <Link href="/login" style={styles.link}>
                Back to sign in
              </Link>
            ) : (
              <>
                <Link href="/signup" style={styles.link}>
                  Create an account
                </Link>
                <Link href="/forgot-password" style={styles.link}>
                  Forgot password?
                </Link>
              </>
            )}
          </View>
        </Card>
      </View>
    </Shell>
  );
}

function PasswordField({
  label,
  value,
  onChange,
  visible,
  onToggleVisibility,
  enforcePolicy,
}: {
  label: string;
  value: string;
  onChange(value: string): void;
  visible: boolean;
  onToggleVisibility(): void;
  enforcePolicy: boolean;
}) {
  return (
    <FieldLabel
      label={label}
      help={enforcePolicy ? 'At least 12 characters with uppercase, lowercase, and a number.' : undefined}
    >
      <View>
        <Input
          // `type` is what drives `secureTextEntry` on the native leaf, so the
          // reveal toggle is a type swap rather than a prop the package exposes.
          type={visible ? 'text' : 'password'}
          aria-label={label}
          maxLength={256}
          value={value}
          onValueChange={onChange}
          style={{ paddingRight: 72 }}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
          onPress={onToggleVisibility}
          style={local.reveal}
        >
          <Text style={styles.link}>{visible ? 'Hide' : 'Show'}</Text>
        </Pressable>
      </View>
    </FieldLabel>
  );
}

const local = StyleSheet.create({
  // `hidden lg:block` on the web — the pitch is decoration beside the form and
  // has no room on a phone. There is no media query here, so it is dropped on
  // narrow layouts by the container's own max width instead.
  pitch: { maxWidth: 520, alignSelf: 'center', width: '100%' },
  card: { width: '100%', maxWidth: 576, alignSelf: 'center' },
  consentRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  switcher: {
    marginTop: 24,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 12,
  },
  reveal: { position: 'absolute', right: 12, top: 0, bottom: 0, justifyContent: 'center' },
});

// The signed-in home, ported from `src/pages/DashboardPage.tsx`: profile setup
// for a brand-new account, then the group list beside the create-a-group form.
import { Button, Checkbox, DateInput, Input, Textarea } from '@ansavva/design-system';
import { Link, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '../api/client';
import { Avatar } from '../components/avatar';
import { FieldLabel } from '../components/field';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { recordPolicyConsent } from '../config/policies';
import { webUrl } from '../config/site';
import { useAuth } from '../context/auth-context';
import { useProfile } from '../context/profile-context';
import { gap, styles } from '../theme/styles';
import type { GroupSummary, Profile } from '../types';
import { pickAvatar } from '../utils/image-picker';
import { sessionKeys, sessionStore } from '../utils/session-store';
import { todayInputValue, validateGroupForm } from '../utils/validation';

export default function DashboardScreen() {
  const auth = useAuth();
  const router = useRouter();
  const { profile, loaded: profileLoaded, setProfile } = useProfile();
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadGroups() {
    setLoading(true);
    setError(null);
    try {
      setGroups(await api.listGroups(await auth.accessToken()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load your groups.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!profileLoaded) return;
    if (!profile) {
      setLoading(false);
      return;
    }
    void loadGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileLoaded, profile?.user_id]);

  const needsProfile = profileLoaded && !profile;

  if (loading || !profileLoaded) return <Shell><LoadingPanel>Preparing your exchanges…</LoadingPanel></Shell>;
  if (needsProfile) return <Shell><ProfileSetup onSaved={setProfile} /></Shell>;

  return (
    <Shell>
      <View style={{ gap: 32 }}>
        <View style={{ gap: gap.md }}>
          <View>
            <Text style={styles.eyebrow}>Your Humbugg home</Text>
            <Text style={[styles.displayLg, { marginTop: 8 }]}>Hello, {profile?.display_name}.</Text>
            <Text style={[styles.bodyMuted, { marginTop: 8 }]}>
              Keep every exchange and secret assignment in one place.
            </Text>
          </View>
        </View>
        <StatusMessage message={error} />
        <View style={{ gap: 24 }}>
          <Card>
            <View style={local.cardHead}>
              <View>
                <Text style={styles.eyebrow}>Your groups</Text>
                <Text style={[styles.heading, { marginTop: 4 }]}>Exchanges in motion</Text>
              </View>
              <View style={styles.countBadge}>
                <Text style={styles.countBadgeText}>{groups.length}</Text>
              </View>
            </View>
            <View style={{ marginTop: 24, gap: 12 }}>
              {groups.map((group) => (
                <Link key={group.group_id} href={`/groups/${group.group_id}`} asChild>
                  <Pressable accessibilityRole="link" style={styles.groupRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.small, styles.semibold]}>{group.name}</Text>
                      <Text style={[styles.smallMuted, { marginTop: 4 }]}>
                        {group.event_date
                          ? new Date(`${group.event_date}T12:00:00`).toLocaleDateString()
                          : 'Date not set'}
                        {' · '}
                        {group.is_organizer ? 'Organizing' : 'Participating'}
                      </Text>
                    </View>
                    <View style={[styles.statusPill, group.status === 'drawn' && styles.statusDrawn]}>
                      <Text style={[styles.statusPillText, group.status === 'drawn' && styles.statusDrawnText]}>
                        {group.status === 'drawn' ? 'Drawn' : 'Open'}
                      </Text>
                    </View>
                  </Pressable>
                </Link>
              ))}
              {!groups.length ? (
                <View style={styles.emptyPanel}>
                  <Text style={styles.headingSm}>No groups yet</Text>
                  <Text style={[styles.bodyMuted, { marginTop: 8, textAlign: 'center' }]}>
                    Create an exchange or open an invitation link to join one.
                  </Text>
                </View>
              ) : null}
            </View>
          </Card>
          <CreateGroup onCreated={(id) => router.push(`/groups/${id}`)} />
        </View>
        <Text style={styles.smallMuted}>
          Manage your photo, display name, and account in{' '}
          <Link href="/settings" style={styles.link}>
            Settings
          </Link>
          .
        </Text>
      </View>
    </Shell>
  );
}

// Profile setup is where policy consent is captured now.
//
// It used to be a checkbox on the signup form, stashed in sessionStorage and
// replayed here. That form belongs to Cognito's hosted pages since #365, and a
// hosted page cannot carry Humbugg's own terms — so the agreement moved to the
// first screen after sign-up that is still ours. It is the same gate in the same
// order: nothing exists for a new account until this form is submitted, and the
// consent rides the very same first `PUT /me` it always did.
function ProfileSetup({ onSaved }: { onSaved(profile: Profile): void }) {
  const auth = useAuth();
  const [name, setName] = useState('');
  const [emailNotifications, setEmailNotifications] = useState(false);
  // Explicit, unchecked by default; gates the first profile create.
  const [consented, setConsented] = useState(false);
  const [avatarDataUrl, setAvatarDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function chooseAvatar() {
    const result = await pickAvatar();
    if (result.kind === 'cancelled') return;
    if (result.kind === 'error') { setError(result.message); return; }
    setAvatarDataUrl(result.dataUrl);
    setError(null);
  }

  async function submit() {
    const displayName = name.trim();
    if (!displayName) { setError('Enter the name your group should see.'); return; }
    if (!consented) {
      setError('Please agree to the Terms of Service and Privacy Policy to continue.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const token = await auth.accessToken();
      // The policy version and the UTC timestamp of the tick, recorded once and
      // immutably by the backend; later saves omit `consent` and are ignored.
      let saved = await api.saveMe(token, displayName, emailNotifications, recordPolicyConsent());
      if (avatarDataUrl) saved = await api.uploadAvatar(token, avatarDataUrl);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save your profile.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card roomy style={{ width: '100%', maxWidth: 576, alignSelf: 'center', marginTop: 48 }}>
      <Text style={styles.eyebrow}>One last detail</Text>
      <Text style={[styles.displayMd, { marginTop: 8 }]}>What should your group call you?</Text>
      <Text style={[styles.bodyMuted, { marginTop: 12 }]}>This is the name other participants will see.</Text>
      <View style={{ marginTop: 28, gap: gap.lg }}>
        <FieldLabel label="Display name">
          <Input aria-label="Display name" maxLength={100} value={name} onValueChange={setName} placeholder="Alex" />
        </FieldLabel>
        <View>
          <Text style={styles.fieldLabelText}>
            Profile picture <Text style={styles.smallMuted}>(optional)</Text>
          </Text>
          <View style={{ marginTop: 8, flexDirection: 'row', alignItems: 'center', gap: 16 }}>
            <Avatar src={avatarDataUrl} name={name} email={auth.email} size={64} bordered />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <Button intent="secondary" size="sm" disabled={busy} onPress={() => void chooseAvatar()}>
                {avatarDataUrl ? 'Change photo' : 'Upload photo'}
              </Button>
              {avatarDataUrl ? (
                <Button intent="ghost" size="sm" disabled={busy} onPress={() => setAvatarDataUrl(null)}>
                  Remove
                </Button>
              ) : null}
            </View>
          </View>
          <Text style={[styles.tiny, { marginTop: 8 }]}>
            PNG, JPEG, or WebP up to 3 MB. You can also add one later.
          </Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
          <Checkbox.Root
            checked={emailNotifications}
            onCheckedChange={(checked) => setEmailNotifications(checked === true)}
            aria-label="Email notifications"
          >
            <Checkbox.Indicator />
          </Checkbox.Root>
          <View style={{ flex: 1 }}>
            <Text style={[styles.small, styles.semibold]}>Email notifications</Text>
            <Text style={styles.smallMuted}>
              Send me optional reminders, group activity, and product updates. Essential account and
              exchange emails always send.
            </Text>
          </View>
        </View>
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
        <StatusMessage message={error} />
        <Button size="lg" disabled={busy} onPress={() => void submit()}>
          {busy ? 'Saving…' : 'Continue'}
        </Button>
      </View>
    </Card>
  );
}

function CreateGroup({ onCreated }: { onCreated(id: string): void }) {
  const auth = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [signupDeadline, setSignupDeadline] = useState('');
  const [spendingLimit, setSpendingLimit] = useState('');
  const minimumDate = todayInputValue();

  async function submit() {
    const values = { name, description, eventDate, signupDeadline, spendingLimit };
    const validationError = validateGroupForm(values, minimumDate);
    if (validationError) { setError(validationError); return; }
    setBusy(true);
    setError(null);
    try {
      const group = await api.createGroup(await auth.accessToken(), {
        name: values.name.trim(),
        description: values.description.trim(),
        event_date: values.eventDate || null,
        signup_deadline: values.signupDeadline || null,
        spending_limit: values.spendingLimit ? Number(values.spendingLimit) : null,
      });
      // The invite link is shown once and never returned again, so it is stashed
      // for the group page to pick up.
      if (group.invite_url) sessionStore.set(sessionKeys.invite(group.group_id), group.invite_url);
      onCreated(group.group_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create the group.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>New exchange</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Start a group</Text>
      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel label="Group name">
          <Input aria-label="Group name" maxLength={120} value={name} onValueChange={setName} placeholder="The Holly Jolly Crew" />
        </FieldLabel>
        <FieldLabel label="A note for the group">
          <Textarea
            aria-label="A note for the group"
            maxLength={1000}
            value={description}
            onValueChange={setDescription}
            placeholder="A little context, a theme, or what to expect."
          />
        </FieldLabel>
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <FieldLabel label="Event date">
              {/*
                `DateInput` replaces the web app's `<Input type="date">`. There is
                no native date input to fall back on, and it is the package's own
                answer to this exact field — a masked text entry with a picker.
              */}
              <DateInput
                aria-label="Event date"
                value={eventDate}
                min={signupDeadline && signupDeadline > minimumDate ? signupDeadline : minimumDate}
                onValueChange={(next) => { setEventDate(next); setError(null); }}
              />
            </FieldLabel>
          </View>
          <View style={{ flex: 1 }}>
            <FieldLabel label="Join by">
              <DateInput
                aria-label="Join by"
                value={signupDeadline}
                min={minimumDate}
                max={eventDate || undefined}
                onValueChange={(next) => { setSignupDeadline(next); setError(null); }}
              />
            </FieldLabel>
          </View>
        </View>
        <Text style={styles.tiny}>The join-by date must be on or before the event date.</Text>
        <FieldLabel label="Spending limit (USD)">
          <Input
            aria-label="Spending limit in US dollars"
            type="number"
            value={spendingLimit}
            onValueChange={setSpendingLimit}
            placeholder="50"
          />
        </FieldLabel>
        <StatusMessage message={error} />
        <Button disabled={busy} onPress={() => void submit()}>
          {busy ? 'Creating…' : 'Create group'}
        </Button>
        <Text style={styles.tiny}>
          Free for up to 6 participants. Larger exchanges use a paid plan — see our{' '}
          <Text style={styles.link} onPress={() => void Linking.openURL(webUrl('/billing'))}>Billing</Text> and{' '}
          <Text style={styles.link} onPress={() => void Linking.openURL(webUrl('/refunds'))}>Refund</Text> policies.
        </Text>
      </View>
    </Card>
  );
}

const local = StyleSheet.create({
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  consentRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
});

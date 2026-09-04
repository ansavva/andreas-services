// Account settings, ported from `src/pages/SettingsPage.tsx`.
//
// The one structural change is the delete-account confirmation: the web app
// hand-rolled a `position: fixed` overlay with its own Escape handler and
// backdrop click. The package ships `AlertDialog` for exactly this — a modal
// confirmation with a destructive action — and it owns the focus trap, the
// dismissal and the `role="alertdialog"` wiring on both platforms, so the
// hand-rolled overlay is gone rather than ported.
import { AlertDialog, Button, Input, Switch } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Text, View } from 'react-native';

import { api } from '../api/client';
import { Avatar } from '../components/avatar';
import { FieldLabel } from '../components/field';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { webUrl } from '../config/site';
import { useAuth } from '../context/auth-context';
import { useProfile } from '../context/profile-context';
import { blends, gap, styles } from '../theme/styles';
import type { Profile } from '../types';
import { pickAvatar } from '../utils/image-picker';

export default function SettingsScreen() {
  const auth = useAuth();
  const { profile, loading, loaded, error, setProfile } = useProfile();

  if (loading && !loaded) return <Shell><LoadingPanel>Loading your settings…</LoadingPanel></Shell>;

  return (
    <Shell>
      <View style={{ width: '100%', maxWidth: 672, alignSelf: 'center', gap: 24 }}>
        <View>
          <Text style={styles.eyebrow}>Your account</Text>
          <Text style={[styles.displayLg, { marginTop: 8 }]}>Settings</Text>
          <Text style={[styles.bodyMuted, { marginTop: 8 }]}>
            Update how you appear to your groups and manage your account.
          </Text>
        </View>
        <StatusMessage message={error} />
        <ProfileSection profile={profile} email={auth.email} onSaved={setProfile} />
        {profile ? <NotificationsSection profile={profile} onSaved={setProfile} /> : null}
        <AccountSection email={auth.email} />
        {profile ? <DangerZone profile={profile} /> : null}
      </View>
    </Shell>
  );
}

function ProfileSection({
  profile,
  email,
  onSaved,
}: {
  profile: Profile | null;
  email: string | null;
  onSaved(profile: Profile): void;
}) {
  const auth = useAuth();
  const [name, setName] = useState(profile?.display_name ?? '');
  const [savingName, setSavingName] = useState(false);
  const [nameStatus, setNameStatus] = useState<{ message: string; tone: 'error' | 'success' } | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  // Optimistic local preview shown immediately while an upload is in flight.
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    setName(profile?.display_name ?? '');
  }, [profile?.display_name]);

  async function saveName() {
    const displayName = name.trim();
    if (!displayName) {
      setNameStatus({ message: 'Enter the name your groups should see.', tone: 'error' });
      return;
    }
    setSavingName(true);
    setNameStatus(null);
    try {
      const saved = await api.saveMe(await auth.accessToken(), displayName);
      onSaved(saved);
      setNameStatus({ message: 'Display name saved.', tone: 'success' });
    } catch (err) {
      setNameStatus({ message: err instanceof Error ? err.message : 'Unable to save your name.', tone: 'error' });
    } finally {
      setSavingName(false);
    }
  }

  async function choosePhoto() {
    const picked = await pickAvatar();
    if (picked.kind === 'cancelled') return;
    if (picked.kind === 'error') { setAvatarError(picked.message); return; }
    setAvatarError(null);
    setAvatarBusy(true);
    try {
      setPreview(picked.dataUrl);
      const saved = await api.uploadAvatar(await auth.accessToken(), picked.dataUrl);
      onSaved(saved);
      setPreview(null);
    } catch (err) {
      setPreview(null);
      setAvatarError(err instanceof Error ? err.message : 'Unable to upload your photo.');
    } finally {
      setAvatarBusy(false);
    }
  }

  async function removePhoto() {
    setAvatarBusy(true);
    setAvatarError(null);
    try {
      const saved = await api.removeAvatar(await auth.accessToken());
      onSaved(saved);
      setPreview(null);
    } catch (err) {
      setAvatarError(err instanceof Error ? err.message : 'Unable to remove your photo.');
    } finally {
      setAvatarBusy(false);
    }
  }

  const shownAvatar = preview ?? profile?.avatar_url ?? null;
  const hasPhoto = Boolean(preview) || Boolean(profile?.avatar_url);

  return (
    <Card>
      <Text style={styles.heading}>Profile</Text>
      <View style={{ marginTop: 24, flexDirection: 'row', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <Avatar src={shownAvatar} name={profile?.display_name} email={email} size={80} bordered />
        <View style={{ gap: 8, flex: 1, minWidth: 200 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <Button
              intent="secondary"
              size="sm"
              disabled={avatarBusy || !profile}
              onPress={() => void choosePhoto()}
            >
              {avatarBusy ? 'Uploading…' : hasPhoto ? 'Change photo' : 'Upload photo'}
            </Button>
            {hasPhoto ? (
              <Button intent="ghost" size="sm" disabled={avatarBusy} onPress={() => void removePhoto()}>
                Remove
              </Button>
            ) : null}
          </View>
          <Text style={styles.tiny}>
            {profile
              ? 'PNG, JPEG, or WebP up to 3 MB. Without a photo, your initials are shown.'
              : 'Save a display name first, then you can add a photo.'}
          </Text>
          <StatusMessage message={avatarError} />
        </View>
      </View>

      <View style={{ marginTop: 28, gap: gap.md }}>
        <FieldLabel label="Display name">
          <Input
            maxLength={100}
            value={name}
            onValueChange={(next) => { setName(next); setNameStatus(null); }}
            placeholder="Alex"
          />
        </FieldLabel>
        {nameStatus ? <StatusMessage message={nameStatus.message} tone={nameStatus.tone} /> : null}
        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={savingName} onPress={() => void saveName()}>
            {savingName ? 'Saving…' : 'Save changes'}
          </Button>
        </View>
      </View>
    </Card>
  );
}

function NotificationsSection({ profile, onSaved }: { profile: Profile; onSaved(profile: Profile): void }) {
  const auth = useAuth();
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ message: string; tone: 'error' | 'success' } | null>(null);
  const enabled = profile.non_essential_emails_enabled;

  async function toggle(next: boolean) {
    setSaving(true);
    setStatus(null);
    try {
      // Send the current display name alongside the preference so PUT /me validates and the change
      // takes effect immediately; onSaved refreshes the shared profile so a reload reflects it.
      const saved = await api.saveMe(await auth.accessToken(), profile.display_name, next);
      onSaved(saved);
      setStatus({
        message: next ? 'Non-essential emails turned on.' : 'Non-essential emails turned off.',
        tone: 'success',
      });
    } catch (err) {
      setStatus({
        message: err instanceof Error ? err.message : 'Unable to update your email preference.',
        tone: 'error',
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Text style={styles.heading}>Email notifications</Text>
      <View style={{ marginTop: 20, flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.small, styles.semibold]}>Send me non-essential emails</Text>
          <Text style={[styles.tiny, { marginTop: 4 }]}>
            Reminders, group-activity notifications, and product news. Turn this off to stop them.
            Essential emails — sign-in and account security, invitations, and “your assignment is
            ready” — always send.
          </Text>
          {/*
            The fallback, said out loud (#137). Turning mail off — or having an address that bounces
            — must not mean missing the exchange, and the reason it does not is that email has never
            been the only copy: every notification is a link to a page that already holds the same
            thing. Someone deciding whether to switch this off deserves to know that before they do,
            not after they have missed a draw.
          */}
          <Text style={[styles.tiny, { marginTop: 8 }]}>
            Nothing is only in an email. Whatever we send, the exchange page shows it too — so if
            mail stops reaching you, sign in and it is all still there.
          </Text>
        </View>
        {/*
          A Switch rather than the web app's checkbox: this is a preference that
          takes effect the moment it moves, with no form to submit, which is the
          distinction the package draws between the two.
        */}
        <Switch.Root
          checked={enabled}
          disabled={saving}
          onCheckedChange={(next: boolean) => void toggle(next)}
          aria-label="Send me non-essential emails"
        >
          <Switch.Thumb />
        </Switch.Root>
      </View>
      {status ? <StatusMessage message={status.message} tone={status.tone} /> : null}
    </Card>
  );
}

function AccountSection({ email }: { email: string | null }) {
  return (
    <Card>
      <Text style={styles.heading}>Account</Text>
      <View style={{ marginTop: 20 }}>
        <FieldLabel
          label="Email"
          help="Your email is managed by sign-in and can't be changed here."
        >
          <Input value={email ?? ''} disabled />
        </FieldLabel>
      </View>
    </Card>
  );
}

function DangerZone({ profile }: { profile: Profile }) {
  const auth = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmName, setConfirmName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const matches = confirmName.trim() === profile.display_name.trim();

  async function deleteAccount() {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(await auth.accessToken());
      // Deletion is idempotent server-side; end the session so the erased account can't keep acting,
      // then return to the marketing home with a confirmation banner.
      await auth.logout();
      setOpen(false);
      void Linking.openURL(webUrl('/?account_deleted=1'));
      router.replace('/login');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to delete your account.');
      setBusy(false);
    }
  }

  return (
    <Card style={{ borderColor: blends.dangerBorder }}>
      <Text style={styles.eyebrow}>Danger zone</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Delete your account</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Deleting your account erases your profile, photo, wishlist, and mailing address. Groups you
        organize are deleted for everyone; where a draw has already happened, your entry is anonymized
        so other participants keep their results. Audit and any legally required financial records are
        retained in anonymized form. This is irreversible. See our{' '}
        <Text style={styles.link} onPress={() => void Linking.openURL(webUrl('/privacy'))}>
          Privacy policy
        </Text>{' '}
        for how deletion and retention work.
      </Text>
      <AlertDialog.Root
        open={open}
        onOpenChange={(next) => {
          if (busy) return;
          setOpen(next);
          if (!next) { setConfirmName(''); setError(null); }
        }}
      >
        <View style={{ marginTop: 16, alignSelf: 'flex-start' }}>
          <AlertDialog.Trigger>Delete my account…</AlertDialog.Trigger>
        </View>
        <AlertDialog.Popup style={{ borderWidth: 1, borderColor: blends.dangerBorder }}>
          <AlertDialog.Title>Delete your account permanently?</AlertDialog.Title>
          <AlertDialog.Description>
            This cannot be undone. Type your display name exactly as shown to confirm.
          </AlertDialog.Description>
          <View style={{ marginTop: 20, gap: 8 }}>
            <Text style={styles.fieldLabelText}>
              Display name: <Text style={styles.semibold}>{profile.display_name}</Text>
            </Text>
            <Input
              aria-label="Confirm your display name"
              value={confirmName}
              onValueChange={setConfirmName}
              placeholder={profile.display_name}
            />
          </View>
          <StatusMessage message={error} />
          <View style={{ marginTop: 24, flexDirection: 'row', justifyContent: 'flex-end', gap: 8 }}>
            <AlertDialog.Close>Cancel</AlertDialog.Close>
            <Button intent="danger" size="sm" disabled={busy || !matches} onPress={() => void deleteAccount()}>
              {busy ? 'Deleting…' : 'Permanently delete'}
            </Button>
          </View>
        </AlertDialog.Popup>
      </AlertDialog.Root>
    </Card>
  );
}

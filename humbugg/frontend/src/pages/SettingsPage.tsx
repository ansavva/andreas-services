import { Button, Input } from '@ansavva/design-system';
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';

import { api } from '../api/client';
import { Avatar } from '../components/Avatar';
import { Card, Shell, StatusMessage } from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import { useProfile } from '../context/ProfileContext';
import type { Profile } from '../types';
import { readFileAsDataUrl, validateAvatarFile } from '../utils/avatar';

export default function SettingsPage() {
  const auth = useAuth();
  const { profile, loading, loaded, error, setProfile } = useProfile();

  if (loading && !loaded) {
    return <Shell><div className="loading-panel">Loading your settings…</div></Shell>;
  }

  return (
    <Shell>
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div>
          <p className="eyebrow">Your account</p>
          <h1 className="mt-2 font-heading text-4xl font-semibold">Settings</h1>
          <p className="mt-2 text-muted">Update how you appear to your groups and manage your account.</p>
        </div>
        <StatusMessage message={error} />
        <ProfileSection profile={profile} email={auth.email} onSaved={setProfile} />
        <AccountSection email={auth.email} />
        {profile && <DangerZone profile={profile} />}
      </div>
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
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  async function saveName(event: FormEvent) {
    event.preventDefault();
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

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so selecting the same file again re-triggers change.
    event.target.value = '';
    if (!file) return;
    const validationError = validateAvatarFile(file);
    if (validationError) {
      setAvatarError(validationError);
      return;
    }
    setAvatarError(null);
    setAvatarBusy(true);
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setPreview(dataUrl);
      const saved = await api.uploadAvatar(await auth.accessToken(), dataUrl);
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
      <h2 className="font-heading text-2xl font-semibold">Profile</h2>
      <div className="mt-6 flex flex-col gap-5 sm:flex-row sm:items-center">
        <Avatar src={shownAvatar} name={profile?.display_name} email={email} size={80} className="border border-line" />
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={onFileChange}
              data-testid="avatar-file-input"
            />
            <Button
              type="button"
              intent="secondary"
              size="sm"
              disabled={avatarBusy || !profile}
              onClick={() => fileInputRef.current?.click()}
            >
              {avatarBusy ? 'Uploading…' : hasPhoto ? 'Change photo' : 'Upload photo'}
            </Button>
            {hasPhoto && (
              <Button type="button" intent="ghost" size="sm" disabled={avatarBusy} onClick={() => void removePhoto()}>
                Remove
              </Button>
            )}
          </div>
          <p className="text-xs text-muted">
            {profile
              ? 'PNG, JPEG, or WebP up to 3 MB. Without a photo, your initials are shown.'
              : 'Save a display name first, then you can add a photo.'}
          </p>
          <StatusMessage message={avatarError} />
        </div>
      </div>

      <form className="mt-7 space-y-4" onSubmit={saveName}>
        <label className="field-label">Display name
          <Input
            value={name}
            required
            minLength={1}
            maxLength={100}
            onChange={(event) => { setName(event.target.value); setNameStatus(null); }}
            placeholder="Alex"
          />
        </label>
        {nameStatus && <StatusMessage message={nameStatus.message} tone={nameStatus.tone} />}
        <Button type="submit" disabled={savingName}>{savingName ? 'Saving…' : 'Save changes'}</Button>
      </form>
    </Card>
  );
}

function AccountSection({ email }: { email: string | null }) {
  return (
    <Card>
      <h2 className="font-heading text-2xl font-semibold">Account</h2>
      <label className="field-label mt-5">Email
        <Input value={email ?? ''} readOnly disabled />
      </label>
      <p className="mt-2 text-xs text-muted">Your email is managed by sign-in and can't be changed here.</p>
    </Card>
  );
}

function DangerZone({ profile }: { profile: Profile }) {
  const auth = useAuth();
  const navigate = useNavigate();
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
      navigate('/?account_deleted=1');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to delete your account.');
      setBusy(false);
    }
  }

  return (
    <Card className="border-danger/30">
      <p className="eyebrow">Danger zone</p>
      <h2 className="mt-1 font-heading text-2xl font-semibold">Delete your account</h2>
      <p className="mt-2 text-sm text-muted">
        Deleting your account erases your profile, photo, wishlist, and mailing address. Groups you organize are
        deleted for everyone; where a draw has already happened, your entry is anonymized so other participants keep
        their results. Audit and any legally required financial records are retained in anonymized form. This is
        irreversible. See our{' '}
        <Link className="text-accent hover:underline" to="/privacy">Privacy policy</Link> for how deletion and
        retention work.
      </p>
      {!open ? (
        <Button intent="danger" size="sm" className="mt-4" onClick={() => setOpen(true)}>Delete my account…</Button>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="field-label">
            Type your display name <span className="font-semibold text-ink">{profile.display_name}</span> to confirm
            <Input
              value={confirmName}
              onChange={(event) => setConfirmName(event.target.value)}
              placeholder={profile.display_name}
              autoFocus
              aria-label="Confirm your display name"
            />
          </label>
          <StatusMessage message={error} />
          <div className="flex gap-2">
            <Button intent="danger" size="sm" disabled={busy || !matches} onClick={() => void deleteAccount()}>
              {busy ? 'Deleting…' : 'Permanently delete'}
            </Button>
            <Button
              intent="secondary"
              size="sm"
              disabled={busy}
              onClick={() => { setOpen(false); setConfirmName(''); setError(null); }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

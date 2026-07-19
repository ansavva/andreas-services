import { Button, Input, Textarea } from '@ansavva/design-system';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';

import { api, ApiError } from '../api/client';
import { Card, Shell, StatusMessage } from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import type { GroupSummary, Profile } from '../types';
import { todayInputValue, validateGroupForm } from '../utils/validation';

export default function DashboardPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const token = await auth.accessToken();
      try { setProfile(await api.getMe(token)); setNeedsProfile(false); }
      catch (err) { if (err instanceof ApiError && err.status === 404) setNeedsProfile(true); else throw err; }
      setGroups(await api.listGroups(token));
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load your account.'); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  if (loading) return <Shell><div className="loading-panel">Preparing your exchanges…</div></Shell>;
  if (needsProfile) return <Shell><ProfileSetup onSaved={(saved) => { setProfile(saved); setNeedsProfile(false); void load(); }} /></Shell>;

  return (
    <Shell>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div><p className="eyebrow">Your Humbugg home</p><h1 className="mt-2 font-heading text-4xl font-semibold">Hello, {profile?.display_name}.</h1><p className="mt-2 text-muted">Keep every exchange and secret assignment in one place.</p></div>
          <Button onClick={() => document.getElementById('new-group')?.scrollIntoView({ behavior: 'smooth' })}>Create a group</Button>
        </div>
        <StatusMessage message={error} />
        <div className="grid gap-6 lg:grid-cols-[1.15fr_.85fr]">
          <Card>
            <div className="flex items-center justify-between"><div><p className="eyebrow">Your groups</p><h2 className="mt-1 font-heading text-2xl font-semibold">Exchanges in motion</h2></div><span className="count-badge">{groups.length}</span></div>
            <div className="mt-6 space-y-3">
              {groups.map((group) => <Link key={group.group_id} to={`/app/groups/${group.group_id}`} className="group-row"><div><h3 className="font-semibold text-ink">{group.name}</h3><p className="mt-1 text-sm text-muted">{group.event_date ? new Date(`${group.event_date}T12:00:00`).toLocaleDateString() : 'Date not set'} · {group.is_organizer ? 'Organizing' : 'Participating'}</p></div><span className={`status-pill ${group.status === 'drawn' ? 'status-drawn' : ''}`}>{group.status === 'drawn' ? 'Drawn' : 'Open'}</span></Link>)}
              {!groups.length && <div className="empty-panel"><p className="font-heading text-xl font-semibold text-ink">No groups yet</p><p className="mt-2">Create an exchange or open an invitation link to join one.</p></div>}
            </div>
          </Card>
          <CreateGroup onCreated={(id) => navigate(`/app/groups/${id}`)} />
        </div>
      </div>
    </Shell>
  );
}

function ProfileSetup({ onSaved }: { onSaved(profile: Profile): void }) {
  const auth = useAuth(); const [name, setName] = useState(''); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); const displayName = name.trim(); if (!displayName) { setError('Enter the name your group should see.'); return; } setBusy(true); setError(null); try { onSaved(await api.saveMe(await auth.accessToken(), displayName)); } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save your profile.'); } finally { setBusy(false); } }
  return <Card className="mx-auto mt-12 max-w-xl p-8"><p className="eyebrow">One last detail</p><h1 className="mt-2 font-heading text-3xl font-semibold">What should your group call you?</h1><p className="mt-3 text-muted">This is the name other participants will see.</p><form className="mt-7 space-y-5" onSubmit={submit}><label className="field-label">Display name<Input required minLength={1} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex" autoFocus /></label><StatusMessage message={error} /><Button type="submit" className="w-full" size="lg" disabled={busy}>{busy ? 'Saving…' : 'Continue'}</Button></form></Card>;
}

function CreateGroup({ onCreated }: { onCreated(id: string): void }) {
  const auth = useAuth(); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [eventDate, setEventDate] = useState(''); const [signupDeadline, setSignupDeadline] = useState('');
  const minimumDate = todayInputValue();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const values = { name: String(data.get('name') ?? ''), description: String(data.get('description') ?? ''), eventDate, signupDeadline, spendingLimit: String(data.get('spending_limit') ?? '') };
    const validationError = validateGroupForm(values, minimumDate);
    if (validationError) { setError(validationError); return; }
    setBusy(true); setError(null);
    try {
      const group = await api.createGroup(await auth.accessToken(), { name: values.name.trim(), description: values.description.trim(), event_date: values.eventDate || null, signup_deadline: values.signupDeadline || null, spending_limit: values.spendingLimit ? Number(values.spendingLimit) : null });
      if (group.invite_url) sessionStorage.setItem(`humbugg:invite:${group.group_id}`, group.invite_url);
      onCreated(group.group_id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create the group.'); } finally { setBusy(false); }
  }
  return <Card id="new-group"><p className="eyebrow">New exchange</p><h2 className="mt-1 font-heading text-2xl font-semibold">Start a group</h2><form className="mt-6 space-y-4" onSubmit={submit}><label className="field-label">Group name<Input name="name" required minLength={1} maxLength={120} placeholder="The Holly Jolly Crew" /></label><label className="field-label">A note for the group<Textarea name="description" maxLength={1000} placeholder="A little context, a theme, or what to expect." /></label><div className="grid grid-cols-2 gap-3"><label className="field-label">Event date<Input name="event_date" type="date" min={signupDeadline && signupDeadline > minimumDate ? signupDeadline : minimumDate} value={eventDate} onChange={(event) => { setEventDate(event.target.value); setError(null); }} /></label><label className="field-label">Join by<Input name="signup_deadline" type="date" min={minimumDate} max={eventDate || undefined} value={signupDeadline} onChange={(event) => { setSignupDeadline(event.target.value); setError(null); }} /></label></div><p className="text-xs text-muted">The join-by date must be on or before the event date.</p><label className="field-label">Spending limit (USD)<Input name="spending_limit" type="number" min="0.01" max="100000" step="0.01" placeholder="50" /></label><StatusMessage message={error} /><Button type="submit" className="w-full" disabled={busy}>{busy ? 'Creating…' : 'Create group'}</Button><p className="text-xs text-muted">Free for up to 6 participants. Larger exchanges use a paid plan — see our <Link className="text-accent hover:underline" to="/billing">Billing</Link> and <Link className="text-accent hover:underline" to="/refunds">Refund</Link> policies.</p></form></Card>;
}

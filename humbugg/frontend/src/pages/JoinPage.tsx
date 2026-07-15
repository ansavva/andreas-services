import { Button } from '@ansavva/design-system';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { api } from '../api/client';
import { Card, Shell, StatusMessage } from '../components/Layout';
import { useAuth } from '../context/AuthContext';

export default function JoinPage() {
  const { groupId = '' } = useParams(); const auth = useAuth(); const navigate = useNavigate();
  const invite = useMemo(() => {
    if (typeof window === 'undefined') return '';
    const fromHash = new URLSearchParams(window.location.hash.slice(1)).get('invite');
    if (fromHash) sessionStorage.setItem(`humbugg:join:${groupId}`, fromHash);
    return fromHash ?? sessionStorage.getItem(`humbugg:join:${groupId}`) ?? '';
  }, [groupId]);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  useEffect(() => { if (!auth.authenticated) sessionStorage.setItem('humbugg:returnTo', `/join/${groupId}`); }, [auth.authenticated, groupId]);
  async function join() { setBusy(true); setError(null); try { await api.joinGroup(await auth.accessToken(), groupId, invite); sessionStorage.removeItem(`humbugg:join:${groupId}`); sessionStorage.removeItem('humbugg:returnTo'); navigate(`/app/groups/${groupId}`); } catch (err) { setError(err instanceof Error ? err.message : 'Unable to join this group.'); } finally { setBusy(false); } }
  return <Shell><Card className="mx-auto mt-12 max-w-xl p-8 text-center"><span className="brand-mark brand-mark-large mx-auto" aria-hidden="true">H</span><p className="eyebrow mt-7">You’re invited</p><h1 className="mt-2 font-heading text-4xl font-semibold">Join this Secret Santa exchange</h1><p className="mx-auto mt-4 max-w-md leading-7 text-muted">Sign in, add your wish list, and let Humbugg keep the surprise safe until draw day.</p>{!invite && <StatusMessage message="This invitation link is incomplete or has expired." />}{auth.authenticated ? <Button className="mt-7 w-full" size="lg" disabled={busy || !invite} onClick={() => void join()}>{busy ? 'Joining…' : 'Join the group'}</Button> : <div className="mt-7 grid gap-3 sm:grid-cols-2"><Button size="lg" onClick={() => navigate('/signup')}>Create account</Button><Button size="lg" intent="secondary" onClick={() => navigate('/login')}>Sign in</Button></div>}<StatusMessage message={error} /></Card></Shell>;
}

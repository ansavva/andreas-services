import { Button, Checkbox, Input, Textarea } from '@ansavva/design-system';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { api, ApiError } from '../api/client';
import { Card, Shell, StatusMessage } from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import type { ExclusionPair, GroupDetail, Membership, PlusPurchaseStatus, RecipientAssignment, RevealAssignment } from '../types';
import { validateAddressForm } from '../utils/validation';

export default function GroupPage() {
  const { groupId = '' } = useParams(); const auth = useAuth(); const navigate = useNavigate();
  const [group, setGroup] = useState<GroupDetail | null>(null); const [me, setMe] = useState<Membership | null>(null); const [assignment, setAssignment] = useState<RecipientAssignment | null>(null);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [success, setSuccess] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState(() => typeof window === 'undefined' ? '' : sessionStorage.getItem(`humbugg:invite:${groupId}`) ?? ''); const [reveal, setReveal] = useState<RevealAssignment[] | null>(null);
  const [purchase, setPurchase] = useState<PlusPurchaseStatus | null>(null);
  const [upgradePrompt, setUpgradePrompt] = useState<string | null>(null);
  const checkoutReturn = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('checkout');
  const intentKey = `humbugg:plus-intent:${groupId}`;

  async function load() {
    setLoading(true); setError(null);
    try {
      const token = await auth.accessToken(); const [detail, membership] = await Promise.all([api.getGroup(token, groupId), api.getMembership(token, groupId)]); setGroup(detail); setMe(membership);
      if (detail.is_organizer) setPurchase(await api.getPlusPurchaseStatus(token, groupId));
      if (detail.status === 'drawn' && membership.is_participating) { try { setAssignment(await api.getAssignment(token, groupId)); } catch (err) { if (!(err instanceof ApiError && err.status === 404)) throw err; } } else setAssignment(null);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load the group.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [groupId]);
  useEffect(() => {
    if (checkoutReturn !== 'success') return;
    let stopped = false; let timer: number | undefined; let attempts = 0;
    async function poll() {
      try {
        const status = await api.getPlusPurchaseStatus(await auth.accessToken(), groupId);
        if (stopped) return;
        setPurchase(status);
        attempts += 1;
        if (status.status === 'pending' && attempts < 10)
          timer = window.setTimeout(() => void poll(), 2000);
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : 'Unable to confirm the Plus purchase.');
      }
    }
    void poll();
    return () => { stopped = true; if (timer !== undefined) window.clearTimeout(timer); };
  }, [auth, checkoutReturn, groupId]);
  async function action(work: (token: string) => Promise<unknown>, message?: string) { setBusy(true); setError(null); setSuccess(null); try { await work(await auth.accessToken()); if (message) setSuccess(message); await load(); return true; } catch (err) { if (err instanceof ApiError && err.code === 'plus_required') { setUpgradePrompt(err.message); sessionStorage.setItem(intentKey, message ?? 'Return to the exchange and retry the Plus action.'); } else setError(err instanceof Error ? err.message : 'The action could not be completed.'); return false; } finally { setBusy(false); } }
  async function startPlusCheckout() {
    setBusy(true); setError(null);
    try {
      const checkout = await api.createPlusCheckout(await auth.accessToken(), groupId);
      window.location.assign(checkout.checkout_url);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to start Checkout.'); setBusy(false); }
  }

  if (loading) return <Shell><div className="loading-panel">Opening your exchange…</div></Shell>;
  if (!group || !me) return <Shell><div className="mx-auto max-w-xl"><StatusMessage message={error ?? 'Group not found.'} /><Link className="text-accent" to="/app">Return to your groups</Link></div></Shell>;
  return (
    <Shell>
      <div className="mb-6"><Link className="text-sm text-muted hover:text-ink" to="/app">← All groups</Link></div>
      <div className="flex flex-col gap-7">
        <section className="group-heading"><div><div className="flex items-center gap-3"><span className={`status-pill ${group.status === 'drawn' ? 'status-drawn' : ''}`}>{group.status === 'drawn' ? 'Draw complete' : 'Open for joining'}</span>{group.is_organizer && <span className="text-sm text-muted">You’re organizing</span>}</div><h1 className="mt-4 font-heading text-4xl font-semibold sm:text-5xl">{group.name}</h1><p className="mt-3 max-w-2xl leading-7 text-muted">{group.description || 'A little holiday magic is taking shape.'}</p></div><div className="group-meta"><span>{group.event_date ? new Date(`${group.event_date}T12:00:00`).toLocaleDateString() : 'Date TBD'}</span><span>{group.spending_limit != null ? `$${group.spending_limit.toFixed(2)} USD` : 'No set limit'}</span><span className="capitalize">{group.plan} plan</span><span>{group.members.filter((member) => member.is_participating).length}{group.plan === 'work' ? '' : ` / ${group.participant_limit}`} participating</span></div></section>
        <StatusMessage message={error} /><StatusMessage message={success} tone="success" />
        {checkoutReturn && <CheckoutRecovery state={checkoutReturn} purchase={purchase} intendedAction={typeof window === 'undefined' ? null : sessionStorage.getItem(intentKey)} onUpgrade={() => void startPlusCheckout()} />}
        {upgradePrompt && <UpgradeOffer reason={upgradePrompt} busy={busy} onUpgrade={() => void startPlusCheckout()} onDismiss={() => setUpgradePrompt(null)} />}

        {assignment && <AssignmentCard assignment={assignment} />}

        {group.is_organizer && <PlusBillingCard group={group} purchase={purchase} busy={busy} onUpgrade={() => void startPlusCheckout()} />}

        <div className="grid gap-7 lg:grid-cols-[1.1fr_.9fr]">
          <Card><p className="eyebrow">Participants</p><h2 className="mt-1 font-heading text-2xl font-semibold">The exchange circle</h2><div className="mt-6 space-y-3">{group.members.map((member) => <div key={member.member_id} className="member-row"><span className="avatar-chip">{member.display_name[0]?.toUpperCase()}</span><div><p className="font-medium">{member.display_name}</p><p className="text-xs text-muted">{member.is_organizer ? 'Organizer' : member.is_participating ? 'Participating' : 'Not participating'}</p></div>{group.is_organizer && group.status === 'open' && !member.is_organizer && <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm text-muted"><Checkbox.Root checked={member.is_participating} onCheckedChange={(checked) => void action((token) => api.setParticipation(token, groupId, member.member_id, checked === true))}><Checkbox.Indicator /></Checkbox.Root>Include</label>}</div>)}</div></Card>
          <WishListForm key={`${me.wishlist ?? ''}|${me.avoidances ?? ''}|${me.address?.line1 ?? ''}`} groupId={groupId} membership={me} busy={busy} onSave={(data) => action((token) => api.updateMembership(token, groupId, data), 'Your gift details are saved.')} onClear={() => action((token) => api.clearMyGroupData(token, groupId), 'Your wishlist and mailing address were cleared.')} />
        </div>

        {group.is_organizer && <OrganizerPanel group={group} inviteUrl={inviteUrl} busy={busy} revealed={reveal} onInvite={() => action(async (token) => { const result = await api.rotateInvite(token, groupId); setInviteUrl(result.invite_url); sessionStorage.setItem(`humbugg:invite:${groupId}`, result.invite_url); }, 'A fresh invitation link is ready.')} onExclusions={(pairs) => action((token) => api.setExclusions(token, groupId, pairs), 'Exclusions updated.')} onDraw={() => action((token) => api.draw(token, groupId), 'The draw is complete.')} onReset={() => { if (window.confirm('Reset every assignment and reopen this group?')) void action((token) => api.reset(token, groupId), 'The group is open again.'); }} onReveal={async (reason) => { setBusy(true); setError(null); try { const result = await api.reveal(await auth.accessToken(), groupId, reason); setReveal(result.assignments); } catch (err) { setError(err instanceof Error ? err.message : 'Unable to reveal assignments.'); } finally { setBusy(false); } }} onDelete={async () => { if (await action((token) => api.deleteGroup(token, groupId))) navigate('/app'); }} />}
      </div>
    </Shell>
  );
}

export function CheckoutRecovery({ state, purchase, intendedAction, onUpgrade }: { state: string; purchase: PlusPurchaseStatus | null; intendedAction: string | null; onUpgrade(): void }) {
  if (state === 'canceled')
    return <Card><p className="font-semibold">Checkout canceled</p><p className="mt-1 text-sm text-muted">Nothing was charged and this exchange is still on its current plan.</p><Button className="mt-4" onClick={onUpgrade}>Return to secure Checkout</Button></Card>;
  if (purchase?.status === 'paid' && purchase.entitlement_id)
    return <Card><p className="font-semibold text-success">Plus is ready</p><p className="mt-1 text-sm text-muted">Your one-time Plus purchase now applies only to this exchange. It does not renew.</p>{intendedAction && <p className="mt-3 text-sm">You can now continue: {intendedAction}</p>}{purchase.receipt_url && <a className="mt-3 inline-block text-accent hover:underline" href={purchase.receipt_url} target="_blank" rel="noreferrer">View Stripe receipt</a>}</Card>;
  if (purchase?.status && ['failed', 'expired', 'refunded'].includes(purchase.status))
    return <Card><p className="font-semibold">Purchase not active</p><p className="mt-1 text-sm text-muted">Stripe reported this payment as {purchase.status}. Your exchange has not been upgraded.</p>{purchase.status !== 'refunded' && <Button className="mt-4" onClick={onUpgrade}>Try Checkout again</Button>}</Card>;
  return <Card><p className="font-semibold">Finalizing your Plus purchase…</p><p className="mt-1 text-sm text-muted">Stripe returned successfully. Humbugg is securely confirming the payment before enabling Plus.</p></Card>;
}

export function UpgradeOffer({ reason, busy, onUpgrade, onDismiss }: { reason: string; busy: boolean; onUpgrade(): void; onDismiss(): void }) {
  return <Card className="border-primary/30" role="region" aria-labelledby="plus-upgrade-title"><p className="eyebrow">One-time exchange upgrade</p><h2 id="plus-upgrade-title" className="mt-1 font-heading text-2xl font-semibold">Unlock Plus for $12</h2><p className="mt-2 text-sm text-muted">{reason}</p><p className="mt-3 text-sm">This is one payment for this exchange only—no subscription and no renewal.</p><ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted"><li>Up to 50 total participants, including you</li><li>Managed email invitations and automatic reminders</li><li>Co-organizers, customization, reusable templates, and late-participant tools</li></ul><div className="mt-5 flex flex-wrap gap-3"><Button disabled={busy} onClick={onUpgrade}>{busy ? 'Opening…' : 'Continue to secure Checkout'}</Button><Button intent="secondary" disabled={busy} onClick={onDismiss}>Not now</Button></div></Card>;
}

function PlusBillingCard({ group, purchase, busy, onUpgrade }: { group: GroupDetail; purchase: PlusPurchaseStatus | null; busy: boolean; onUpgrade(): void }) {
  const atFreeLimit = group.plan === 'free' && group.members.filter((member) => member.is_participating).length >= 6;
  return <Card><p className="eyebrow">Exchange billing</p><h2 className="mt-1 font-heading text-2xl font-semibold">{group.plan === 'plus' ? 'Plus for this exchange' : 'Free plan'}</h2>{group.plan === 'plus' ? <><p className="mt-2 text-sm text-muted">Plus was purchased once for this exchange. It does not renew or apply to other exchanges.</p>{purchase?.status && <p className="mt-3 text-sm capitalize">Payment status: {purchase.status}</p>}{purchase?.receipt_url && <a className="mt-3 inline-block text-accent hover:underline" href={purchase.receipt_url} target="_blank" rel="noreferrer">View Stripe receipt</a>}</> : <><p className="mt-2 text-sm text-muted">Free includes six total participants. Plus is a one-time $12 purchase for this exchange and raises the limit to 50.</p>{atFreeLimit && <p className="mt-3 font-medium">This exchange is at the Free participant limit.</p>}<Button className="mt-4" disabled={busy} onClick={onUpgrade}>See Plus and upgrade</Button></>}</Card>;
}

function AssignmentCard({ assignment }: { assignment: RecipientAssignment }) {
  const address = Object.values(assignment.address ?? {}).filter(Boolean).join(', ');
  return <section className="assignment-card"><p className="text-sm font-semibold uppercase tracking-[.2em] text-primary-text/70">Your secret recipient</p><h2 className="mt-2 font-heading text-4xl font-semibold">{assignment.display_name}</h2><div className="mt-7 grid gap-5 md:grid-cols-3"><div><p className="assignment-label">Gift ideas</p><p>{assignment.wishlist || 'No ideas added yet.'}</p></div><div><p className="assignment-label">Please avoid</p><p>{assignment.avoidances || 'Nothing listed.'}</p></div><div><p className="assignment-label">Delivery address</p><p>{address || 'No address provided.'}</p></div></div></section>;
}

function WishListForm({ groupId, membership, busy, onSave, onClear }: { groupId: string; membership: Membership; busy: boolean; onSave(data: Record<string, unknown>): void; onClear(): void }) {
  const [wishlist, setWishlist] = useState(membership.wishlist ?? ''); const [avoidances, setAvoidances] = useState(membership.avoidances ?? ''); const [validationError, setValidationError] = useState<string | null>(null); const address = membership.address ?? {};
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const addressValues = { line1: String(data.get('line1') ?? ''), line2: String(data.get('line2') ?? ''), city: String(data.get('city') ?? ''), region: String(data.get('region') ?? ''), postalCode: String(data.get('postal_code') ?? ''), country: String(data.get('country') ?? '') }; const error = validateAddressForm(addressValues); if (error) { setValidationError(error); return; } setValidationError(null); onSave({ wishlist: wishlist.trim(), avoidances: avoidances.trim(), address: { line1: addressValues.line1.trim(), line2: addressValues.line2.trim(), city: addressValues.city.trim(), region: addressValues.region.trim(), postal_code: addressValues.postalCode.trim(), country: addressValues.country.trim() } }); }
  return <Card><p className="eyebrow">Your details</p><h2 className="mt-1 font-heading text-2xl font-semibold">Help your giver choose well</h2><p className="mt-2 text-sm text-muted">Only your assigned giver can see these details after the draw.</p><form className="mt-6 space-y-4" onSubmit={submit}><label className="field-label">Gift ideas<Textarea maxLength={2000} value={wishlist} onChange={(e) => setWishlist(e.target.value)} placeholder="Books, colors, hobbies, links…" /></label><label className="field-label">Things to avoid<Textarea maxLength={2000} value={avoidances} onChange={(e) => setAvoidances(e.target.value)} placeholder="Allergies, dislikes, duplicate items…" /></label><details className="rounded-xl border border-line p-4"><summary className="cursor-pointer font-medium">Optional mailing address</summary><p className="mt-2 text-xs text-muted">If you add an address, the address line, city, postal code, and country are required.</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><Input name="line1" maxLength={150} defaultValue={address.line1} placeholder="Address line 1" className="sm:col-span-2" /><Input name="line2" maxLength={150} defaultValue={address.line2} placeholder="Address line 2" className="sm:col-span-2" /><Input name="city" maxLength={100} defaultValue={address.city} placeholder="City" /><Input name="region" maxLength={100} defaultValue={address.region} placeholder="State / region" /><Input name="postal_code" maxLength={32} defaultValue={address.postal_code} placeholder="Postal code" /><Input name="country" maxLength={100} defaultValue={address.country} placeholder="Country" /></div></details><StatusMessage message={validationError} /><Button type="submit" className="w-full" disabled={busy}>Save my details</Button></form><div className="mt-4 border-t border-line pt-4"><p className="text-xs text-muted">Clear the wishlist, avoidances, and mailing address you have saved for this exchange. This does not remove you from the group.</p><Button intent="secondary" size="sm" className="mt-3" disabled={busy} onClick={() => { if (window.confirm('Clear your wishlist, avoidances, and mailing address for this exchange?')) onClear(); }}>Clear my wishlist &amp; address</Button></div></Card>;
}

interface OrganizerProps { group: GroupDetail; inviteUrl: string; busy: boolean; revealed: RevealAssignment[] | null; onInvite(): void; onExclusions(pairs: string[][]): void; onDraw(): void; onReset(): void; onReveal(reason: string): Promise<void>; onDelete(): Promise<void>; }
function OrganizerPanel(props: OrganizerProps) {
  const { group } = props; const [first, setFirst] = useState(''); const [second, setSecond] = useState(''); const [pairs, setPairs] = useState<ExclusionPair[]>(group.exclusions); const [reason, setReason] = useState(''); const [confirmingDelete, setConfirmingDelete] = useState(false); const [deleteAnnouncement, setDeleteAnnouncement] = useState(''); const deleteArmedAt = useRef(0);
  const names = useMemo(() => Object.fromEntries(group.members.map((m) => [m.member_id, m.display_name])), [group.members]);
  function addPair() { if (first && second && first !== second && !pairs.some((pair) => pair.includes(first) && pair.includes(second))) setPairs([...pairs, [first, second]]); }
  useEffect(() => {
    if (!confirmingDelete) return;
    const timeout = window.setTimeout(() => {
      deleteArmedAt.current = 0;
      setConfirmingDelete(false);
      setDeleteAnnouncement('Delete confirmation expired.');
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [confirmingDelete]);
  async function handleDeleteClick() {
    if (!confirmingDelete) {
      deleteArmedAt.current = Date.now();
      setConfirmingDelete(true);
      setDeleteAnnouncement('Deletion armed. Click Confirm delete within five seconds to permanently delete this group.');
      return;
    }
    if (Date.now() - deleteArmedAt.current < 500) return;
    setConfirmingDelete(false);
    setDeleteAnnouncement('Deleting group.');
    await props.onDelete();
    deleteArmedAt.current = 0;
  }
  return <Card className="border-primary/20"><div className="flex flex-col justify-between gap-4 sm:flex-row"><div><p className="eyebrow">Organizer tools</p><h2 className="mt-1 font-heading text-2xl font-semibold">Prepare the draw</h2></div><div className="self-end sm:self-auto"><Button className={`delete-button w-40 shrink-0 ${confirmingDelete ? 'delete-button-armed' : ''}`} intent="danger" size="sm" disabled={props.busy} aria-label={confirmingDelete ? 'Confirm permanent group deletion within five seconds' : 'Delete group'} onClick={() => void handleDeleteClick()}><span className="delete-button-label">{props.busy ? 'Deleting…' : confirmingDelete ? 'Confirm delete' : 'Delete group'}</span>{confirmingDelete && !props.busy && <span className="delete-button-timer" aria-hidden="true" />}</Button><span className="sr-only" aria-live="polite">{deleteAnnouncement}</span></div></div>
    {group.status === 'open' ? <div className="mt-7 grid gap-7 lg:grid-cols-2"><div><h3 className="font-semibold">Invitation link</h3><p className="mt-1 text-sm text-muted">Links are shown once. Rotating invalidates the previous link.</p>{props.inviteUrl ? <div className="mt-3 flex gap-2"><Input readOnly value={props.inviteUrl} /><Button intent="secondary" onClick={() => void navigator.clipboard.writeText(props.inviteUrl)}>Copy</Button></div> : <Button className="mt-3" intent="secondary" onClick={props.onInvite}>Create a fresh link</Button>}</div><div><h3 className="font-semibold">Pair exclusions</h3><p className="mt-1 text-sm text-muted">People in a pair cannot draw one another.</p><div className="mt-3 grid grid-cols-[1fr_1fr_auto] gap-2"><select className="select-control" value={first} onChange={(e) => setFirst(e.target.value)}><option value="">Choose person</option>{group.members.filter((m) => m.is_participating).map((m) => <option key={m.member_id} value={m.member_id}>{m.display_name}</option>)}</select><select className="select-control" value={second} onChange={(e) => setSecond(e.target.value)}><option value="">Choose person</option>{group.members.filter((m) => m.is_participating).map((m) => <option key={m.member_id} value={m.member_id}>{m.display_name}</option>)}</select><Button intent="secondary" onClick={addPair}>Add</Button></div><div className="mt-3 flex flex-wrap gap-2">{pairs.map((pair, index) => <button className="pair-chip" key={`${pair[0]}-${pair[1]}`} onClick={() => setPairs(pairs.filter((_, item) => item !== index))}>{names[pair[0]]} + {names[pair[1]]} ×</button>)}</div><Button className="mt-4" intent="secondary" onClick={() => props.onExclusions(pairs)}>Save exclusions</Button></div><div className="lg:col-span-2 rounded-xl bg-surface-alt p-5"><h3 className="font-semibold">Ready to draw?</h3><p className="mt-1 text-sm text-muted">Drawing locks the roster and exclusions. Every person sees only their own recipient.</p><Button className="mt-4" size="lg" disabled={props.busy} onClick={props.onDraw}>Create private assignments</Button></div></div> : <div className="mt-7 grid gap-7 lg:grid-cols-2"><div className="rounded-xl bg-surface-alt p-5"><h3 className="font-semibold">Need to change the group?</h3><p className="mt-2 text-sm text-muted">Resetting clears every assignment and reopens the roster.</p><Button className="mt-4" intent="secondary" onClick={props.onReset}>Reset the draw</Button></div><div className="rounded-xl border border-danger/30 p-5"><h3 className="font-semibold">Emergency reveal</h3><p className="mt-2 text-sm text-muted">This action is permanently audited. Give a reason before viewing all assignments.</p><Textarea className="mt-3" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="Why is this reveal necessary?" /><Button className="mt-3" intent="danger" disabled={reason.trim().length === 0 || props.busy} onClick={() => props.onReveal(reason)}>Reveal all assignments</Button></div>{props.revealed && <div className="lg:col-span-2"><h3 className="font-semibold">Revealed assignments</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">{props.revealed.map((item) => <div className="rounded-xl bg-surface-alt p-4" key={item.giver.member_id}><span className="font-medium">{item.giver.display_name}</span><span className="mx-2 text-muted">→</span><span>{item.recipient.display_name}</span></div>)}</div></div>}</div>}
  </Card>;
}

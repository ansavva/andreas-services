// Managed invitations (#574) — the organizer sends the invitations instead of pasting a link.
//
// The Free way to invite somebody is to copy one link and send it yourself, which works and scales
// to six. This is the Plus way: addresses go in, Humbugg sends and tracks each one, and the
// organizer can see which have bounced or gone unanswered rather than guessing from who has not
// turned up.
//
// The backend has been able to do this since August 2026 and no screen called it. That is the whole
// defect this file closes, so it deliberately covers every endpoint that exists — create, resend
// and revoke — rather than the one that is easiest to render.
import { Badge, Button, Textarea } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, styles } from '../theme/styles';
import type { GroupDetail, InvitationStatus, ManagedInvitation } from '../types';
import { FieldLabel } from './field';
import { isPlusRequired, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/**
 * What each status means to the person reading it, rather than what it is called in the table.
 *
 * "sent" and "delivered" are deliberately different: a delivered invitation is the mail provider's
 * word that it arrived, which is the difference between chasing the address and chasing the person.
 */
const STATUS: Record<InvitationStatus, { label: string; intent: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  sent: { label: 'Sent', intent: 'neutral' },
  delivered: { label: 'Delivered', intent: 'neutral' },
  accepted: { label: 'Joined', intent: 'success' },
  bounced: { label: 'Bounced', intent: 'danger' },
  expired: { label: 'Expired', intent: 'warning' },
  revoked: { label: 'Revoked', intent: 'neutral' },
};

/**
 * Split whatever was pasted into addresses.
 *
 * People paste from a mail client, a spreadsheet column or a chat message, so the separator is
 * whichever of comma, semicolon, newline or space happens to be there. Validation is the server's —
 * it owns the rule and names the offending address in its error, and a second regex here would only
 * be a different opinion about what an address is.
 */
export function splitAddresses(raw: string): string[] {
  const seen = new Set<string>();
  return raw
    .split(/[,;\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .filter((part) => {
      const key = part.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

export function InvitationsPanel({
  group,
  onChanged,
}: {
  group: GroupDetail;
  /** The roster and the counts above change when somebody is invited or an invitation is pulled. */
  onChanged?(): void;
}) {
  const auth = useAuth();
  const [invitations, setInvitations] = useState<ManagedInvitation[] | null>(null);
  const [needsPlus, setNeedsPlus] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInvitations(await api.listInvitations(await auth.accessToken(), group.group_id));
      setNeedsPlus(false);
    } catch (err) {
      // A 402 is not a failure to report — it is the answer, and it has its own card below.
      if (isPlusRequired(err)) setNeedsPlus(true);
      else setError(err instanceof Error ? err.message : 'Unable to read the invitations.');
    }
  }, [auth, group.group_id]);

  useEffect(() => { void load(); }, [load]);

  const addresses = splitAddresses(draft);

  async function send() {
    setBusy('send');
    setError(null);
    setSent(null);
    try {
      const result = await api.createInvitations(await auth.accessToken(), group.group_id, addresses);
      setDraft('');
      setSent(
        result.invitations.length === 1
          ? `Invitation sent to ${result.invitations[0].email}.`
          : `${result.invitations.length} invitations sent.`,
      );
      await load();
      onChanged?.();
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      // Every refusal here names the address or the reason — a duplicate, an address already
      // invited, one that is not an address. Showing the server's own words is what makes the
      // fix obvious, so nothing is rewritten into "Something went wrong".
      else setError(err instanceof Error ? err.message : 'The invitations could not be sent.');
    } finally {
      setBusy(null);
    }
  }

  async function act(invitation: ManagedInvitation, what: 'resend' | 'revoke') {
    setBusy(invitation.invitation_id);
    setError(null);
    setSent(null);
    try {
      const token = await auth.accessToken();
      if (what === 'resend') {
        await api.resendInvitation(token, group.group_id, invitation.invitation_id);
        setSent(`Sent again to ${invitation.email}.`);
      } else {
        await api.revokeInvitation(token, group.group_id, invitation.invitation_id);
      }
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That could not be done.');
    } finally {
      setBusy(null);
    }
  }

  if (needsPlus)
    return (
      <PlusLockedNote
        reason="Sending and tracking invitations is part of Plus."
        action="invite people by email and see who has not answered"
        isOwner={group.is_owner}
      />
    );

  // Nothing is drawn until the first read lands. An empty list and an unread one look identical,
  // and "Nobody has been invited yet" is a claim rather than a placeholder.
  if (invitations === null) return null;

  const outstanding = invitations.filter(
    (invitation) => invitation.status !== 'accepted' && invitation.status !== 'revoked',
  );

  return (
    <Card>
      <Text style={styles.eyebrow}>Invitations</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>
        {outstanding.length === 0 ? 'Invite people by email' : `${outstanding.length} still open`}
      </Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Humbugg sends each one and tells you what happened to it. They join by following their own
        link, so you never have to pass one on.
      </Text>

      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel
          label="Email addresses"
          help="One per line, or separated by commas — however they come out of wherever you keep them."
        >
          <Textarea
            maxLength={4000}
            value={draft}
            onValueChange={(value) => { setDraft(value); setError(null); setSent(null); }}
            placeholder={'robin@example.com\nsam@example.com'}
          />
        </FieldLabel>

        <StatusMessage message={error} />
        {/* Announced, not merely shown: `StatusMessage` carries the live region, which is the
            only way somebody using a screen reader learns that the send worked. */}
        <StatusMessage message={sent} tone="success" />

        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={busy !== null || addresses.length === 0} onPress={() => void send()}>
            {busy === 'send'
              ? 'Sending…'
              : addresses.length <= 1
                ? 'Send the invitation'
                : `Send ${addresses.length} invitations`}
          </Button>
        </View>
      </View>

      {invitations.length > 0 ? (
        <View style={{ marginTop: 28, gap: 12 }}>
          {invitations.map((invitation) => (
            <View key={invitation.invitation_id} style={styles.memberRow}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.small, styles.semibold]}>{invitation.email}</Text>
                <Text style={styles.tiny}>{detail(invitation)}</Text>
              </View>
              <Badge intent={STATUS[invitation.status].intent} size="sm">
                {STATUS[invitation.status].label}
              </Badge>
              {invitation.status === 'accepted' || invitation.status === 'revoked' ? null : (
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <Button
                    intent="secondary"
                    size="sm"
                    disabled={busy !== null}
                    onPress={() => void act(invitation, 'resend')}
                  >
                    Send again
                  </Button>
                  <Button
                    intent="secondary"
                    size="sm"
                    disabled={busy !== null}
                    onPress={() => void act(invitation, 'revoke')}
                  >
                    Withdraw
                  </Button>
                </View>
              )}
            </View>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

/** The one line under an address: what happened to this invitation, and when. */
function detail(invitation: ManagedInvitation): string {
  if (invitation.status === 'accepted')
    return invitation.accepted_at ? `Joined ${when(invitation.accepted_at)}` : 'Joined';
  if (invitation.status === 'bounced') return 'The address did not accept it — check it for a typo';
  if (invitation.status === 'expired') return `Expired ${when(invitation.expires_at)}`;
  if (invitation.status === 'revoked') return 'Withdrawn — the link no longer works';
  const sent = invitation.last_sent_at ? `Sent ${when(invitation.last_sent_at)}` : 'Sent';
  return `${sent} · expires ${when(invitation.expires_at)}`;
}

function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return 'at an unknown time';
  return at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

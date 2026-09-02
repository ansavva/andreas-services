// The structured wishlist (#128), on the model added in #127. Two audiences and two components:
// `WishListPanel` is the owner editing their own list, `RecipientWishList` is the assigned giver
// reading it after the draw.
import { Badge, Button, Input, Select, Textarea } from '@ansavva/design-system';
import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '../api/client';
import { DangerButton } from '../components/danger-button';
import { FieldLabel } from '../components/field';
import { Card } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import { brand } from '../theme/theme';
import type { RecipientWish, Wish, WishClaimState } from '../types';
import {
  emptyWishForm,
  formatPrice,
  kindLabel,
  linkHost,
  priorityLabel,
  toCreateInput,
  toUpdateInput,
  validateWishForm,
  wishKinds,
  wishPriorities,
  type WishFormValues,
} from '../utils/wish';

export function WishListPanel({ groupId }: { groupId: string }) {
  const auth = useAuth();
  const [wishes, setWishes] = useState<Wish[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setWishes(await api.listWishes(await auth.accessToken(), groupId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load your wishlist.');
    } finally {
      setLoading(false);
    }
  }

  // Keyed on the group alone. Depending on the auth object instead reloads the list on every
  // render that hands back a new one, which is a request storm rather than a refresh.
  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [groupId]);

  async function run(work: (token: string) => Promise<unknown>, announcement: string) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await work(await auth.accessToken());
      await load();
      setStatus(announcement);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That change could not be saved.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Reorder sends the whole order because the API requires a complete permutation — a partial one
  // would leave the wishes it did not name at stale positions.
  function move(index: number, direction: -1 | 1) {
    if (!wishes) return;
    const next = [...wishes];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void run(
      (token) => api.reorderWishes(token, groupId, next.map((wish) => wish.wish_id)),
      `Moved ${next[target].title} ${direction === -1 ? 'down' : 'up'}.`,
    );
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>Your wishlist</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>What you would love</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Only your assigned giver sees this, and only after the draw. Put the thing you want most at
        the top.
      </Text>

      <Text accessibilityLiveRegion="polite" style={local.srOnly}>{status ?? ''}</Text>
      <StatusMessage message={error} />

      {loading ? (
        <View style={[styles.emptyPanel, { marginTop: 20 }]}>
          <Text style={styles.smallMuted}>Loading your wishlist…</Text>
        </View>
      ) : wishes === null ? null : wishes.length > 0 ? (
        <View style={{ marginTop: 20, gap: gap.sm }}>
          {wishes.map((wish, index) =>
            editing === wish.wish_id ? (
              <WishForm
                key={wish.wish_id}
                heading={`Edit ${wish.title}`}
                initial={formFromWish(wish)}
                busy={busy}
                submitLabel="Save changes"
                onCancel={() => setEditing(null)}
                onSubmit={async (values) => {
                  const saved = await run(
                    (token) => api.updateWish(token, groupId, wish.wish_id, toUpdateInput(values)),
                    `${values.title.trim()} updated.`,
                  );
                  if (saved) setEditing(null);
                }}
              />
            ) : (
              <WishRow
                key={wish.wish_id}
                wish={wish}
                busy={busy}
                isFirst={index === 0}
                isLast={index === wishes.length - 1}
                onEdit={() => { setEditing(wish.wish_id); setAdding(false); }}
                onMoveUp={() => move(index, -1)}
                onMoveDown={() => move(index, 1)}
                onRemove={() =>
                  void run(
                    (token) => api.deleteWish(token, groupId, wish.wish_id),
                    `${wish.title} removed from your wishlist.`,
                  )
                }
              />
            ),
          )}
        </View>
      ) : (
        <View style={[styles.emptyPanel, { marginTop: 20 }]}>
          <Text style={[styles.small, styles.semibold]}>Nothing on your list yet</Text>
          <Text style={[styles.smallMuted, { marginTop: 6, textAlign: 'center' }]}>
            Add a few things — a link, a rough idea, anything at all. It makes your giver&apos;s job
            much easier.
          </Text>
        </View>
      )}

      {adding ? (
        <View style={{ marginTop: gap.sm }}>
          <WishForm
            heading="Add a wish"
            initial={emptyWishForm}
            busy={busy}
            // Only the ADD form reads links. Editing an existing wish is for correcting what is
            // there, and re-fetching a page to overwrite it is the opposite of that.
            groupId={groupId}
            submitLabel="Add to my list"
            onCancel={() => setAdding(false)}
            onSubmit={async (values) => {
              const saved = await run(
                (token) => api.createWish(token, groupId, toCreateInput(values)),
                `${values.title.trim()} added to your wishlist.`,
              );
              if (saved) setAdding(false);
            }}
          />
        </View>
      ) : (
        <View style={{ marginTop: 20, alignSelf: 'flex-start' }}>
          <Button disabled={busy} onPress={() => { setAdding(true); setEditing(null); }}>
            Add a wish
          </Button>
        </View>
      )}
    </Card>
  );
}

function WishRow({
  wish,
  busy,
  isFirst,
  isLast,
  onEdit,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  wish: Wish;
  busy: boolean;
  isFirst: boolean;
  isLast: boolean;
  onEdit(): void;
  onMoveUp(): void;
  onMoveDown(): void;
  onRemove(): void;
}) {
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const price = formatPrice(wish.price_cents, wish.currency);
  const host = linkHost(wish.url);

  return (
    <View style={local.row}>
      <View style={{ flex: 1, gap: 6 }}>
        <Text style={[styles.small, styles.semibold]}>{wish.title}</Text>
        <View style={local.chips}>
          <Badge size="sm">{kindLabel[wish.kind]}</Badge>
          {wish.priority !== 'normal' ? (
            <Badge size="sm" intent={wish.priority === 'high' ? 'primary' : 'neutral'}>
              {priorityLabel[wish.priority]}
            </Badge>
          ) : null}
          {wish.quantity > 1 ? <Badge size="sm">×{wish.quantity}</Badge> : null}
          {price ? <Text style={styles.tiny}>{price}</Text> : null}
        </View>
        {host ? (
          <Pressable
            accessibilityRole="link"
            accessibilityLabel={`Open ${wish.title} on ${host}`}
            onPress={() => { if (wish.url) void Linking.openURL(wish.url); }}
          >
            <Text style={[styles.tiny, { color: brand.primary }]}>{host} ↗</Text>
          </Pressable>
        ) : null}
        {wish.details ? <Text style={styles.tiny}>{wish.details}</Text> : null}
      </View>

      <View style={local.rowActions}>
        {/*
          Up/down rather than drag-and-drop: it is reachable by keyboard and by a screen reader, it
          works the same on a phone and in a browser, and every press is one complete reorder the
          server can accept or reject. A drag would be neither.
        */}
        <Button
          intent="secondary"
          size="sm"
          disabled={busy || isFirst}
          accessibilityLabel={`Move ${wish.title} up`}
          onPress={onMoveUp}
        >
          ↑
        </Button>
        <Button
          intent="secondary"
          size="sm"
          disabled={busy || isLast}
          accessibilityLabel={`Move ${wish.title} down`}
          onPress={onMoveDown}
        >
          ↓
        </Button>
        <Button
          intent="secondary"
          size="sm"
          disabled={busy}
          accessibilityLabel={`Edit ${wish.title}`}
          onPress={onEdit}
        >
          Edit
        </Button>
        {/* One press arms, the next commits — the same confirmation shape the rest of this app uses. */}
        <DangerButton
          size="sm"
          disabled={busy}
          accessibilityLabel={
            confirmingRemove ? `Confirm removing ${wish.title}` : `Remove ${wish.title}`
          }
          onPress={() => {
            if (!confirmingRemove) { setConfirmingRemove(true); return; }
            setConfirmingRemove(false);
            onRemove();
          }}
        >
          {confirmingRemove ? 'Confirm' : 'Remove'}
        </DangerButton>
      </View>
    </View>
  );
}

function WishForm({
  heading,
  initial,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
  groupId,
}: {
  heading: string;
  initial: WishFormValues;
  busy: boolean;
  submitLabel: string;
  onSubmit(values: WishFormValues): void;
  onCancel(): void;
  /** Absent on the edit form: reading a link is for turning a paste into a new wish. */
  groupId?: string;
}) {
  const auth = useAuth();
  const [values, setValues] = useState<WishFormValues>(initial);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  // The host the fields came from, once they have. Shown because a title somebody else's server
  // wrote should not sit in this form looking like something the owner typed.
  const [source, setSource] = useState<string | null>(null);
  const set = <K extends keyof WishFormValues>(key: K, value: WishFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  /**
   * Fills what the page offered and leaves everything editable (#129).
   *
   * Only ever fills a field the owner has not already filled — a preview that overwrites a title
   * somebody typed is a preview that loses their work. And a failure is not an error: the form was
   * a manual form a moment ago and still is.
   */
  async function readLink() {
    if (!groupId || values.url.trim().length === 0) return;
    setReading(true);
    setValidationError(null);
    try {
      const preview = await api.previewWishUrl(await auth.accessToken(), groupId, values.url.trim());
      setSource(preview.host);
      setValues((current) => ({
        ...current,
        title: current.title.trim() === '' ? preview.title ?? '' : current.title,
        imageUrl: current.imageUrl.trim() === '' ? preview.image_url ?? '' : current.imageUrl,
        url: preview.canonical_url ?? current.url,
        price:
          current.price.trim() === '' && preview.price_cents != null
            ? (preview.price_cents / 100).toFixed(2)
            : current.price,
      }));
    } catch (err) {
      // A refusal the server could decide from the URL alone is worth showing — the owner typed it
      // and can fix it. Anything else already came back as an empty preview.
      setValidationError(err instanceof Error ? err.message : 'That link could not be read.');
    } finally {
      setReading(false);
    }
  }

  return (
    <View style={local.form}>
      <Text style={[styles.small, styles.semibold]}>{heading}</Text>
      <View style={{ marginTop: gap.md, gap: gap.md }}>
        <FieldLabel label="What is it?">
          <Input
            aria-label="What is it?"
            maxLength={200}
            value={values.title}
            onValueChange={(value) => set('title', value)}
            placeholder="A really good chef's knife"
          />
        </FieldLabel>
        <FieldLabel label="Kind">
          <Select
            aria-label="Kind"
            options={wishKinds}
            value={values.kind}
            onValueChange={(value) => set('kind', value as WishFormValues['kind'])}
          />
        </FieldLabel>
        <FieldLabel label="How much would you love it?">
          <Select
            aria-label="How much would you love it?"
            options={wishPriorities}
            value={values.priority}
            onValueChange={(value) => set('priority', value as WishFormValues['priority'])}
          />
        </FieldLabel>
        <FieldLabel label="Link" hint="(optional)">
          <Input
            aria-label="Link"
            maxLength={2048}
            value={values.url}
            onValueChange={(value) => set('url', value)}
            placeholder="https://…"
          />
        </FieldLabel>
        {groupId ? (
          <View style={{ alignSelf: 'flex-start', gap: 6 }}>
            <Button
              intent="secondary"
              size="sm"
              disabled={reading || busy || values.url.trim().length === 0}
              onPress={() => void readLink()}
            >
              {reading ? 'Reading…' : 'Fill from the link'}
            </Button>
            {source ? (
              // Whose page this came from, said plainly. The fields below are a stranger's words
              // until the owner edits them, and a preview whose source is invisible is a way to make
              // them look like Humbugg's.
              <Text style={styles.tiny}>Filled from {source}. Change anything you like.</Text>
            ) : null}
          </View>
        ) : null}
        <FieldLabel label="Image link" hint="(optional)">
          <Input
            aria-label="Image link"
            maxLength={2048}
            value={values.imageUrl}
            onValueChange={(value) => set('imageUrl', value)}
            placeholder="https://…"
          />
        </FieldLabel>
        <FieldLabel label="Rough price" hint="(optional)">
          <Input
            aria-label="Rough price"
            value={values.price}
            onValueChange={(value) => set('price', value)}
            placeholder="25.00"
          />
        </FieldLabel>
        <FieldLabel label="How many?">
          <Input
            aria-label="How many?"
            value={values.quantity}
            onValueChange={(value) => set('quantity', value)}
            placeholder="1"
          />
        </FieldLabel>
        <FieldLabel label="Notes" hint="(optional)">
          <Textarea
            aria-label="Notes"
            maxLength={1000}
            value={values.details}
            onValueChange={(value) => set('details', value)}
            placeholder="Size, colour, which edition, anything that helps"
          />
        </FieldLabel>
        <StatusMessage message={validationError} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: gap.xs }}>
          <Button
            disabled={busy}
            onPress={() => {
              const problem = validateWishForm(values);
              setValidationError(problem);
              if (!problem) onSubmit(values);
            }}
          >
            {submitLabel}
          </Button>
          <Button intent="secondary" disabled={busy} onPress={onCancel}>Cancel</Button>
        </View>
      </View>
    </View>
  );
}

/**
 * The giver's view after the draw, with their own purchase claims (#130).
 *
 * The claim controls appear here and nowhere else, which is the same argument the API makes with
 * its route: the only list you may mark up is the one your assignment gives you. The wishlist owner
 * has no component that could render this, because `Wish` carries no claim to render.
 */
export function RecipientWishList({
  wishes,
  busy = false,
  onClaim,
  onRelease,
}: {
  wishes: RecipientWish[];
  busy?: boolean;
  /** Omit both to render the list read-only — which is what an emergency reveal gets. */
  onClaim?(wishId: string, state: WishClaimState, quantity: number): void;
  onRelease?(wishId: string): void;
}) {
  if (wishes.length === 0) {
    return <Text style={styles.assignmentText}>No specific wishes added.</Text>;
  }
  return (
    <View style={{ gap: gap.sm }}>
      {/* Said once for the list rather than under every item: the reassurance is about the
          feature, not about any particular gift, and repeating it per wish is noise. */}
      {onClaim ? (
        <Text style={[styles.tiny, { color: blends.assignmentLabel }]}>
          What you mark here is yours alone — they never see it, and it is only for this draw.
        </Text>
      ) : null}
      {wishes.map((wish) => {
        const price = formatPrice(wish.price_cents, wish.currency);
        const host = linkHost(wish.url);
        return (
          <View key={wish.wish_id} style={local.recipientRow}>
            <Text style={[styles.small, styles.semibold, { color: brand.primaryText }]}>
              {wish.title}
            </Text>
            <View style={local.chips}>
              <Badge size="sm">{kindLabel[wish.kind]}</Badge>
              {wish.priority !== 'normal' ? (
                <Badge size="sm" intent={wish.priority === 'high' ? 'primary' : 'neutral'}>
                  {priorityLabel[wish.priority]}
                </Badge>
              ) : null}
              {wish.quantity > 1 ? <Badge size="sm">×{wish.quantity}</Badge> : null}
              {price ? <Text style={[styles.tiny, { color: brand.primaryText }]}>{price}</Text> : null}
            </View>
            {host ? (
              <Pressable
                accessibilityRole="link"
                accessibilityLabel={`Open ${wish.title} on ${host}`}
                onPress={() => { if (wish.url) void Linking.openURL(wish.url); }}
              >
                <Text style={[styles.tiny, { color: brand.primaryText, textDecorationLine: 'underline' }]}>
                  {host} ↗
                </Text>
              </Pressable>
            ) : null}
            {wish.details ? (
              <Text style={[styles.tiny, { color: brand.primaryText }]}>{wish.details}</Text>
            ) : null}
            {onClaim && onRelease ? (
              <ClaimControls
                wish={wish}
                busy={busy}
                onClaim={onClaim}
                onRelease={onRelease}
              />
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

/**
 * One wish's claim row.
 *
 * The buttons are the design system's `secondary` intent rather than `primary`: this sits on the
 * assignment card, whose background IS `primary`, so a primary button would be dark green on dark
 * green. Nothing is hand-rolled to get there — the intent that reads on this surface is the one
 * the package already ships.
 */
function ClaimControls({
  wish,
  busy,
  onClaim,
  onRelease,
}: {
  wish: RecipientWish;
  busy: boolean;
  onClaim(wishId: string, state: WishClaimState, quantity: number): void;
  onRelease(wishId: string): void;
}) {
  // Defaults to the whole wish, which is what a giver almost always means. The picker only exists
  // when there is a choice to make.
  const [quantity, setQuantity] = useState(String(wish.claim?.quantity ?? wish.quantity));
  const chosen = Math.min(Math.max(Number(quantity) || wish.quantity, 1), wish.quantity);
  const claim = wish.claim ?? null;

  return (
    <View style={{ gap: gap.xs, marginTop: 4 }}>
      {claim ? (
        <Text style={styles.assignmentLabel}>
          {claim.state === 'purchased' ? 'You bought this' : 'You are getting this'}
          {wish.quantity > 1 ? ` · ${claim.quantity} of ${wish.quantity}` : ''}
        </Text>
      ) : null}

      {wish.quantity > 1 && claim?.state !== 'purchased' ? (
        <View style={{ maxWidth: 200 }}>
          <Select
            aria-label={`How many of ${wish.title}`}
            options={Array.from({ length: wish.quantity }, (_, index) => ({
              value: String(index + 1),
              label: `${index + 1} of ${wish.quantity}`,
            }))}
            value={String(chosen)}
            onValueChange={(next) => setQuantity(next ?? String(wish.quantity))}
          />
        </View>
      ) : null}

      <View style={local.rowActions}>
        {claim?.state !== 'planned' && claim?.state !== 'purchased' ? (
          <Button
            intent="secondary"
            size="sm"
            disabled={busy}
            onPress={() => onClaim(wish.wish_id, 'planned', chosen)}
          >
            I'm getting this
          </Button>
        ) : null}
        {claim?.state !== 'purchased' ? (
          <Button
            intent="secondary"
            size="sm"
            disabled={busy}
            onPress={() => onClaim(wish.wish_id, 'purchased', chosen)}
          >
            I bought it
          </Button>
        ) : null}
        {claim ? (
          <Button intent="secondary" size="sm" disabled={busy} onPress={() => onRelease(wish.wish_id)}>
            Undo
          </Button>
        ) : null}
      </View>

    </View>
  );
}

function formFromWish(wish: Wish): WishFormValues {
  return {
    title: wish.title,
    kind: wish.kind,
    url: wish.url ?? '',
    imageUrl: wish.image_url ?? '',
    price: wish.price_cents != null ? (wish.price_cents / 100).toFixed(2) : '',
    quantity: String(wish.quantity),
    priority: wish.priority,
    details: wish.details ?? '',
  };
}

const local = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'flex-start',
    gap: gap.sm,
    borderWidth: 1,
    borderColor: brand.line,
    borderRadius: 12,
    padding: gap.md,
  },
  rowActions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: gap.xs },
  chips: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: gap.xs },
  form: { borderWidth: 1, borderColor: brand.line, borderRadius: 12, padding: gap.md },
  recipientRow: {
    gap: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.18)',
    paddingTop: gap.sm,
  },
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 },
});

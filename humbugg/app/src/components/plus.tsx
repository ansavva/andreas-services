// Buying Plus (#141) — the offer, the checkout round trip, and the organizer's billing area.
//
// Three things live here because they have to agree with each other. The offer states a price; the
// billing area states what was paid; the return states whether it worked. Split across screens,
// they drift — and the first one to drift would be the price.
//
// **Nothing in this file states a price of its own.** The amount, the currency and the participant
// limits come from `GET /api/plans`, which reads the same configuration Stripe charges against. A
// literal "$12" here would keep rendering after a price change, on the one surface where being
// wrong about the price is not a cosmetic bug.
//
// **Plus is one payment for one exchange.** It does not renew and it does not follow the organizer
// to their next exchange. Every state below says so in words, because the shape a purchase button
// usually has is a subscription's and the wrong assumption is the expensive one.
import { Badge, Button } from '@ansavva/design-system';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import * as WebBrowser from 'expo-web-browser';

import { api, ApiError } from '../api/client';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import { brand } from '../theme/theme';
import type { GroupDetail, PaymentStatus, PlanDefinition, PlusPurchaseStatus } from '../types';
import { plusIntent } from '../utils/plus-intent';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/**
 * What Plus buys, in the order an organizer meets it. One line per shipped backend capability
 * (`PlanCapability` plus the participant ceiling) — this list is a promise the API keeps, so a
 * capability that is not built does not belong on it.
 */
export const PLUS_BENEFITS = [
  'Invite by email, and see who has joined, not opened, or bounced.',
  'Automatic reminders, so you are not the one chasing people.',
  'Co-organizers who can run the exchange alongside you.',
  'Your own greeting, instructions and colours on what everyone sees.',
  'Save the whole setup as a template and start next year from it.',
  'Add someone after the draw, changing as few matches as possible.',
] as const;

/** A 402 from the API. The backend raises exactly one code for "this needs Plus". */
export function isPlusRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 402;
}

/** `1200, 'USD'` → `$12`. Whole amounts drop the cents; $12.00 reads like a subscription row. */
export function formatPrice(cents: number, currency: string): string {
  const amount = cents / 100;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    // Intl is present in Hermes and in every browser this ships to, but a formatter that throws
    // must not take the upgrade offer down with it.
    return `${amount} ${currency}`;
  }
}

// ---------------------------------------------------------------------------
// Opening Checkout
// ---------------------------------------------------------------------------

/**
 * Leaves for Stripe, and says how the app expects to come back.
 *
 * The two platforms come back differently and the difference is not cosmetic. On web this is a
 * full-page navigation, exactly like the hosted sign-in: Stripe returns the browser to
 * `/organize/{groupId}?checkout=…` and the screen reads that query. On native the `https://` return
 * URL cannot re-enter the app — `openAuthSessionAsync` intercepts a custom scheme, not a web
 * origin — so nothing is intercepted at all: the browser is opened, and when the user closes it the
 * screen re-reads the purchase from the API. That makes the API the source of truth on native and
 * the query string only a hint on web, which is the right way round: the query says what Stripe
 * *told the browser*, and only the webhook decides whether Plus is on.
 */
async function openCheckout(url: string): Promise<'left' | 'returned'> {
  if (Platform.OS === 'web') {
    globalThis.location.assign(url);
    return 'left';
  }
  try {
    await WebBrowser.openBrowserAsync(url);
  } catch {
    // A device with no browser to hand still gets a link it can act on.
    await Linking.openURL(url);
  }
  return 'returned';
}

/**
 * Starting a purchase, from anywhere.
 *
 * `start(action)` records what the organizer was trying to do before it opens Checkout, so the
 * return can say "You can now …" instead of dropping them back on a page with no memory of why
 * they left. `onReturned` fires only on native, where closing the browser is the whole signal.
 */
export function usePlusCheckout(groupId: string, onReturned?: () => void) {
  const auth = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(
    async (action: string) => {
      setBusy(true);
      setError(null);
      try {
        await plusIntent.save(groupId, action);
        const session = await api.createPlusCheckout(await auth.accessToken(), groupId);
        const outcome = await openCheckout(session.checkout_url);
        if (outcome === 'returned') onReturned?.();
      } catch (err) {
        // Nothing was opened, so nothing is pending; a remembered intent would resurface on the
        // organizer's next visit attached to a purchase that never started.
        await plusIntent.clear();
        setError(err instanceof Error ? err.message : 'Checkout could not be opened.');
      } finally {
        setBusy(false);
      }
    },
    [auth, groupId, onReturned],
  );

  return { start, busy, error };
}

// ---------------------------------------------------------------------------
// The offer
// ---------------------------------------------------------------------------

/**
 * The upgrade offer. Rendered two ways, from the same component so they cannot say different
 * things: as a panel in the organizer's billing area, and inline the moment an action is refused
 * with `plus_required` — where `reason` carries the server's own sentence about what was blocked.
 */
export function PlusUpgradeOffer({
  plan,
  reason,
  busy,
  error,
  onUpgrade,
  action,
  cta = 'Upgrade this exchange',
  freeLimit,
}: {
  /** The Plus plan as the server defines it. Null while `/api/plans` is still loading or failed. */
  plan: PlanDefinition | null;
  /** Why this appeared, in the API's words. Omitted when the organizer opened the offer themselves. */
  reason?: string | null;
  busy: boolean;
  error?: string | null;
  onUpgrade(action: string): void;
  /** Phrased to follow "You can now …" — it is read back verbatim after a successful return. */
  action: string;
  cta?: string;
  /** The Free ceiling, for the one line that compares the two plans. Server-sourced like the price. */
  freeLimit?: number | null;
}) {
  const price = plan ? formatPrice(plan.price_cents, plan.currency) : null;
  return (
    <View style={{ gap: gap.md }}>
      {reason ? (
        <View accessibilityRole="alert" style={local.reason}>
          <Text style={[styles.small, styles.semibold]}>{reason}</Text>
        </View>
      ) : null}

      <View style={local.offerHeading}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={styles.eyebrow}>Plus</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>
            {price ? `${price} once, for this exchange` : 'One payment, for this exchange'}
          </Text>
        </View>
        <Badge intent="neutral" size="sm">One-time</Badge>
      </View>

      {/*
        The sentence that stops the wrong assumption. A purchase button of this shape is nearly
        always a subscription's, so "does not renew" and "this exchange only" are stated before the
        benefits rather than in small print under them.
      */}
      <Text style={styles.small}>
        A single payment. It does not renew, nothing is stored to charge again, and it applies to
        this exchange only — your next exchange starts on Free.
      </Text>

      <View style={{ gap: 8 }}>
        {plan && freeLimit ? (
          <Benefit>
            Up to {plan.participant_limit} participants, instead of {freeLimit}.
          </Benefit>
        ) : null}
        {PLUS_BENEFITS.map((benefit) => (
          <Benefit key={benefit}>{benefit}</Benefit>
        ))}
      </View>

      <StatusMessage message={error} />

      {/*
        A plan with no Stripe price behind it cannot be bought: `CreatePlusCheckoutAsync` refuses
        with "Plus purchasing is not configured". Saying so is better than a button whose only
        outcome is that sentence in red — the capabilities above are still worth reading, and this
        is the state a fresh environment is in before its Stripe product exists.
      */}
      {plan && !plan.price_id ? (
        <Text style={[styles.small, styles.semibold]}>
          Plus is not on sale yet. Everything above is built and waiting on payments being switched
          on; nothing about this exchange changes in the meantime.
        </Text>
      ) : (
        <>
          <View style={{ alignSelf: 'flex-start' }}>
            <Button size="lg" disabled={busy} onPress={() => onUpgrade(action)}>
              {busy ? 'Opening Stripe…' : price ? `${cta} — ${price}` : cta}
            </Button>
          </View>
          <Text style={styles.tiny}>
            Payment is handled by Stripe. Humbugg never sees your card details.
          </Text>
        </>
      )}
    </View>
  );
}

function Benefit({ children }: { children: React.ReactNode }) {
  return (
    <View style={local.benefit}>
      <Text style={local.tick}>✓</Text>
      <Text style={[styles.small, { flex: 1 }]}>{children}</Text>
    </View>
  );
}

/** The plan catalogue, fetched once per mount. A failure is silent: the offer still stands, it
 * just cannot name the price, and refusing to render an upgrade path because a price lookup failed
 * would be worse than an unpriced button that opens a Checkout showing the real amount. */
export function usePlanCatalogue(): PlanDefinition[] | null {
  const auth = useAuth();
  const [plans, setPlans] = useState<PlanDefinition[] | null>(null);
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const catalogue = await api.listPlans(await auth.accessToken());
        if (alive) setPlans(catalogue);
      } catch {
        /* an unpriced offer is still an offer */
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return plans;
}

/**
 * The offer raised by a refusal — what an organizer sees the moment the API answers 402.
 *
 * Self-contained on purpose: any screen that can perform a plan-gated action can render this from
 * the error it already caught, without also learning how to fetch plans or open Stripe. `reason` is
 * the server's own sentence ("Plus is required for participant 7…"), so what is refused and what is
 * offered can never disagree.
 *
 * Both platforms end at the billing area. On web Stripe navigates there itself; on native the
 * browser simply closes, so this routes there with the same query Stripe would have used, and one
 * confirm loop covers both.
 */
export function PlusRefusalCard({
  groupId,
  reason,
  action,
  onNavigate,
}: {
  groupId: string;
  reason: string;
  /** Phrased to follow "You can now …". */
  action: string;
  /** Where to send a native return. The web return is Stripe's own redirect. */
  onNavigate(path: string): void;
}) {
  const plans = usePlanCatalogue();
  const checkout = usePlusCheckout(groupId, () =>
    onNavigate(`/organize/${groupId}?checkout=success`),
  );
  return (
    <Card style={{ borderColor: blends.primaryBorder }}>
      <PlusUpgradeOffer
        plan={plans?.find((plan) => plan.code === 'plus') ?? null}
        freeLimit={plans?.find((plan) => plan.code === 'free')?.participant_limit ?? null}
        reason={reason}
        action={action}
        busy={checkout.busy}
        error={checkout.error}
        onUpgrade={(intent) => void checkout.start(intent)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// The organizer's billing area
// ---------------------------------------------------------------------------

/** What the app does about a `?checkout=` value, once. */
type ReturnPhase = 'idle' | 'confirming' | 'active' | 'unconfirmed' | 'canceled' | 'rejected';

/** Six tries, two seconds apart — a webhook that has not landed in twelve seconds is not racing. */
const CONFIRM_ATTEMPTS = 6;
const CONFIRM_DELAY_MS = 2_000;

const REJECTED: PaymentStatus[] = ['failed', 'expired', 'refunded'];

export function PlusBillingPanel({
  group,
  checkout,
  onEntitled,
}: {
  group: GroupDetail;
  /** The `checkout` query Stripe returned with: `success`, `canceled`, or absent. Web only. */
  checkout?: string | null;
  /** Called once Plus is confirmed active, so the screen can reload the plan it already rendered. */
  onEntitled(): void;
}) {
  const auth = useAuth();
  const [status, setStatus] = useState<PlusPurchaseStatus | null>(null);
  const plans = usePlanCatalogue();
  const [loadError, setLoadError] = useState<string | null>(null);
  const [phase, setPhase] = useState<ReturnPhase>(checkout === 'canceled' ? 'canceled' : 'idle');
  const [resumed, setResumed] = useState<string | null>(null);
  // React mounts effects twice in development. Confirming twice is harmless but polls Stripe's
  // status twice as fast for no reason, and would announce success twice to a screen reader.
  const confirming = useRef(false);
  const alive = useRef(true);
  // The poll's own sleep. Held so unmounting stops the loop rather than leaving a timer to fire
  // into a screen that is gone — and, under jest, to keep the process alive after the test ends.
  const sleeping = useRef<ReturnType<typeof setTimeout> | null>(null);

  const plus = plans?.find((candidate) => candidate.code === 'plus') ?? null;
  const free = plans?.find((candidate) => candidate.code === 'free') ?? null;

  const refresh = useCallback(async (): Promise<PlusPurchaseStatus | null> => {
    const token = await auth.accessToken();
    const next = await api.getPlusPurchaseStatus(token, group.group_id);
    if (alive.current) setStatus(next);
    return next;
  }, [auth, group.group_id]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (sleeping.current) clearTimeout(sleeping.current);
    };
  }, []);

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      if (alive.current)
        setLoadError(err instanceof Error ? err.message : 'Billing could not be loaded.');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group.group_id]);

  /**
   * The confirm loop, shared by both platforms' returns.
   *
   * It waits for `entitlement_id`, never for `status === 'paid'` alone. The webhook writes the
   * entitlement and the group's plan in one transaction, and the entitlement is what the backend's
   * capability check reads — so a paid row without one is a purchase Stripe has taken money for and
   * Humbugg has not applied yet. Announcing "Plus is active" there would be a promise the very next
   * request answers with a 402.
   */
  const confirm = useCallback(async () => {
    if (confirming.current) return;
    confirming.current = true;
    setPhase('confirming');
    try {
      for (let attempt = 0; attempt < CONFIRM_ATTEMPTS; attempt += 1) {
        const next = await refresh().catch(() => null);
        if (!alive.current) return;
        if (next?.entitlement_id) {
          setResumed((await plusIntent.load(group.group_id))?.action ?? null);
          await plusIntent.clear();
          setPhase('active');
          onEntitled();
          return;
        }
        if (next?.status && REJECTED.includes(next.status)) {
          await plusIntent.clear();
          setPhase('rejected');
          return;
        }
        await new Promise<void>((resolve) => {
          sleeping.current = setTimeout(resolve, CONFIRM_DELAY_MS);
        });
      }
      if (alive.current) setPhase('unconfirmed');
    } finally {
      confirming.current = false;
    }
  }, [group.group_id, onEntitled, refresh]);

  const checkoutFlow = usePlusCheckout(group.group_id, () => void confirm());

  // Web returns through the query string; native returns by closing the browser, which
  // `usePlusCheckout` reports instead.
  useEffect(() => {
    if (checkout === 'success') void confirm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkout]);

  const entitled = Boolean(status?.entitlement_id) || group.plan !== 'free';
  const atFreeCeiling =
    group.plan === 'free' &&
    group.members.filter((member) => member.is_participating).length >= group.participant_limit;

  return (
    <Card style={entitled ? undefined : { borderColor: blends.primaryBorder }}>
      <View style={local.offerHeading}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={styles.eyebrow}>Billing</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>
            {entitled ? 'Plus is on for this exchange' : 'This exchange is on Free'}
          </Text>
        </View>
        <Badge intent={entitled ? 'success' : 'neutral'} size="sm">
          {entitled ? 'Plus' : 'Free'}
        </Badge>
      </View>

      <View style={{ marginTop: 20, gap: gap.md }}>
        <StatusMessage message={loadError} />
        <ReturnBanner phase={phase} resumed={resumed} receiptUrl={status?.receipt_url ?? null} />

        {entitled ? (
          <PaidSummary status={status} />
        ) : (
          <>
            {atFreeCeiling ? (
              <View style={local.reason}>
                <Text style={[styles.small, styles.semibold]}>
                  This exchange is full. Free includes {free?.participant_limit ?? group.participant_limit}{' '}
                  participants, the organizer among them — nobody else can join until it moves to Plus.
                </Text>
              </View>
            ) : null}
            {/* Only when no return is being narrated: the banner above is already telling that
                story, and two sentences about one payment read as two payments. */}
            {phase === 'idle' ? <PendingSummary status={status} /> : null}
            <PlusUpgradeOffer
              plan={plus}
              freeLimit={free?.participant_limit ?? group.participant_limit}
              busy={checkoutFlow.busy}
              error={checkoutFlow.error}
              onUpgrade={(action) => void checkoutFlow.start(action)}
              action={
                atFreeCeiling
                  ? 'invite everyone else who is waiting to join'
                  : 'use every Plus capability on this exchange'
              }
              cta={status?.status === 'pending' ? 'Finish the payment' : 'Upgrade this exchange'}
            />
          </>
        )}
      </View>
    </Card>
  );
}

/** The four checkout returns, said plainly. `idle` renders nothing at all. */
function ReturnBanner({
  phase,
  resumed,
  receiptUrl,
}: {
  phase: ReturnPhase;
  resumed: string | null;
  receiptUrl: string | null;
}) {
  if (phase === 'idle') return null;

  if (phase === 'canceled') {
    return (
      <Banner tone="neutral">
        Checkout was canceled, so nothing was charged. This exchange is exactly as you left it, and
        you can upgrade whenever you want.
      </Banner>
    );
  }

  if (phase === 'confirming') {
    return <Banner tone="neutral">Confirming your payment with Stripe…</Banner>;
  }

  if (phase === 'rejected') {
    return (
      <Banner tone="danger">
        That payment did not go through, so Plus is not on and nothing is owed. Trying again opens a
        fresh Checkout.
      </Banner>
    );
  }

  if (phase === 'unconfirmed') {
    return (
      <Banner tone="neutral">
        Stripe has your payment and Humbugg has not finished applying it. This usually takes under a
        minute — reload this page and it will say Plus. If it still does not in ten minutes, email
        support and quote {receiptUrl ? 'your Stripe receipt' : 'this exchange'}; you will not be
        charged twice.
      </Banner>
    );
  }

  // Deliberately not a second "Plus is on for this exchange" — the heading directly above says
  // that. What this adds is the fact the heading cannot carry: that the charge is finished, and
  // what the organizer came here to do before Plus stopped them.
  return (
    <Banner tone="success">
      Payment confirmed. That is the only charge for this exchange — nothing renews.
      {resumed ? ` You can now ${resumed}.` : ''}
    </Banner>
  );
}

function Banner({ tone, children }: { tone: 'success' | 'danger' | 'neutral'; children: React.ReactNode }) {
  const background =
    tone === 'success' ? blends.primaryWash : tone === 'danger' ? blends.dangerWash : brand.surfaceAlt;
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[local.banner, { backgroundColor: background }]}
    >
      <Text style={styles.small}>{children}</Text>
    </View>
  );
}

/** What an organizer wants after paying: proof, and a receipt they can file. */
function PaidSummary({ status }: { status: PlusPurchaseStatus | null }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.small}>
        Paid once for this exchange. It does not renew, and a new exchange starts on Free.
      </Text>
      {status?.receipt_url ? (
        <Pressable
          accessibilityRole="link"
          onPress={() => void Linking.openURL(status.receipt_url as string)}
        >
          <Text style={styles.link}>View your Stripe receipt</Text>
        </Pressable>
      ) : (
        <Text style={styles.tiny}>
          Stripe emails the receipt to the address you paid with; the link appears here once Stripe
          sends it.
        </Text>
      )}
      {status?.updated_at ? (
        <Text style={styles.tiny}>Last updated {formatWhen(status.updated_at)}.</Text>
      ) : null}
    </View>
  );
}

/** An unfinished or rejected purchase, above the offer that would retry it. */
function PendingSummary({ status }: { status: PlusPurchaseStatus | null }) {
  if (!status?.status) return null;
  if (status.status === 'paid') {
    return (
      <Banner tone="neutral">
        Stripe has taken the payment and Plus is still being applied. Reload in a moment.
      </Banner>
    );
  }
  if (status.status === 'pending') {
    return (
      <Banner tone="neutral">
        A payment for this exchange was started and not finished. Nothing has been charged.
      </Banner>
    );
  }
  if (status.status === 'refunded') {
    return (
      <Banner tone="neutral">
        That purchase was refunded, so this exchange is back on Free. You can buy Plus for it again.
      </Banner>
    );
  }
  return (
    <Banner tone="danger">
      The last payment {status.status === 'expired' ? 'expired before it completed' : 'did not go through'}.
      Nothing was charged.
    </Banner>
  );
}

function formatWhen(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleString();
}

const local = StyleSheet.create({
  offerHeading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.sm,
  },
  benefit: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  tick: { color: brand.primary, fontFamily: styles.semibold.fontFamily, fontSize: 14, lineHeight: 20 },
  banner: { borderRadius: 12, padding: 16 },
  reason: {
    borderRadius: 12,
    padding: 16,
    backgroundColor: blends.primaryWash,
    borderWidth: 1,
    borderColor: blends.primaryBorder,
  },
});

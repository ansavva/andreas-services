import type { PlanCode, PolicyConsent } from '../types';

/**
 * Single source of truth for Humbugg's published policies.
 *
 * NOTE FOR MAINTAINERS: the values below are launch placeholders. Confirm the
 * legal/merchant entity name, the effective date, and the support contact
 * before publishing, and have the policy copy reviewed by counsel. Bump
 * POLICY_VERSION and POLICY_EFFECTIVE_DATE whenever the wording changes.
 */

// Policy version + effective date recorded on every policy page.
export const POLICY_VERSION = '2026.1';
// ISO date the current policies take effect. Placeholder — confirm before publishing.
export const POLICY_EFFECTIVE_DATE = '2026-07-01';

// Display / merchant identity shown in the policies. Placeholder — confirm the
// registered business name that will appear on card statements.
export const BUSINESS_NAME = 'Humbugg';
// Support contact surfaced in every policy. Placeholder — confirm the address.
export const SUPPORT_EMAIL = 'support@humbugg.com';

// Launch market. Humbugg launches US-only, priced in US dollars.
export const SERVICE_COUNTRY = 'United States';
export const SERVICE_CURRENCY = 'USD';

/**
 * Builds the consent record captured when a user actively agrees to the Terms of Service and Privacy
 * Policy at signup. `version` references POLICY_VERSION so the recorded consent stays in sync with the
 * published policies; `accepted_at` is a UTC ISO-8601 timestamp of the moment of agreement.
 */
export function recordPolicyConsent(now: Date = new Date()): PolicyConsent {
  return { version: POLICY_VERSION, accepted_at: now.toISOString() };
}

/** Human-readable effective date, e.g. "July 1, 2026". */
export function policyEffectiveDateLabel(): string {
  return new Date(`${POLICY_EFFECTIVE_DATE}T12:00:00Z`).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

export interface LegalLink {
  to: string;
  label: string;
}

// Ordered list of policy pages, reused by the footer and the in-page policy nav.
export const LEGAL_LINKS: readonly LegalLink[] = [
  { to: '/terms', label: 'Terms of Service' },
  { to: '/privacy', label: 'Privacy Policy' },
  { to: '/billing', label: 'Billing Terms' },
  { to: '/refunds', label: 'Refund Policy' },
] as const;

export interface PlanFact {
  code: PlanCode;
  name: string;
  price: string;
  cadence: string;
  summary: string;
}

// Plan facts referenced by the Billing terms so the figures live in one place.
export const PLANS: readonly PlanFact[] = [
  {
    code: 'free',
    name: 'Free',
    price: '$0',
    cadence: 'always free',
    summary: 'Up to 6 total participants in a single exchange, including the organizer.',
  },
  {
    code: 'plus',
    name: 'Plus',
    price: '$12',
    cadence: 'one-time charge per exchange',
    summary: 'A one-time upgrade for a single exchange, raising the limit to 50 total participants.',
  },
  {
    code: 'work',
    name: 'Work',
    price: '$99',
    cadence: 'per year, automatically renewing',
    summary:
      'An annual plan for organizers running exchanges throughout the year; it renews each year until canceled.',
  },
] as const;

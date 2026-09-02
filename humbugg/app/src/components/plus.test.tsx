// Buying Plus (#141).
//
// The behaviours pinned here are the ones that cost money or trust if they drift:
//  - the price on screen is the server's, never a constant in this app;
//  - the copy never implies a renewal or a purchase that covers every exchange;
//  - "Plus is active" is said only when the ENTITLEMENT exists, not when Stripe says paid — the
//    backend gates capabilities on the entitlement, so the other reading promises a 402;
//  - every checkout return has words: canceled, paid, rejected, and still-confirming;
//  - a purchase carries the organizer's intent across Stripe and reads it back.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Platform } from 'react-native';
import * as WebBrowser from 'expo-web-browser';

const mocks = {
  listPlans: jest.fn(),
  getPlusPurchaseStatus: jest.fn(),
  createPlusCheckout: jest.fn(),
  onEntitled: jest.fn(),
};

jest.mock('../api/client', () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, _code: string, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    api: {
      listPlans: (...args: unknown[]) => mocks.listPlans(...args),
      getPlusPurchaseStatus: (...args: unknown[]) => mocks.getPlusPurchaseStatus(...args),
      createPlusCheckout: (...args: unknown[]) => mocks.createPlusCheckout(...args),
    },
    ApiError,
  };
});

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('./shell', () => {
  const { View } = require('react-native');
  return { Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View> };
});

const intentStore: { value: string | null } = { value: null };
jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    getItem: () => Promise.resolve(intentStore.value),
    setItem: (_key: string, value: string) => {
      intentStore.value = value;
      return Promise.resolve();
    },
    removeItem: () => {
      intentStore.value = null;
      return Promise.resolve();
    },
  },
}));

import { PlusBillingPanel, formatPrice, isPlusRequired } from './plus';
import type { GroupDetail, PlanDefinition, PlusPurchaseStatus } from '../types';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

const PLANS: PlanDefinition[] = [
  {
    code: 'free',
    name: 'Free',
    participant_limit: 6,
    marketed_as_unlimited: false,
    price_cents: 0,
    currency: 'USD',
    billing_cadence: 'free',
  },
  {
    code: 'plus',
    name: 'Plus',
    participant_limit: 50,
    marketed_as_unlimited: false,
    price_cents: 1_200,
    currency: 'USD',
    billing_cadence: 'one_time',
    price_id: 'price_plus',
  },
];

function group(overrides: Partial<GroupDetail> = {}): GroupDetail {
  return {
    group_id: 'g1',
    name: 'Office Exchange',
    status: 'open',
    currency: 'USD',
    plan: 'free',
    participant_limit: 6,
    is_organizer: true,
    is_owner: true,
    created_at: 'now',
    updated_at: 'now',
    description: '',
    exclusions: [],
    members: [{ member_id: 'm1', display_name: 'Ana', is_organizer: true, is_participating: true }],
    ...overrides,
  };
}

function members(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    member_id: `m${index}`,
    display_name: `Person ${index}`,
    is_organizer: index === 0,
    is_participating: true,
  }));
}

const NO_PURCHASE: PlusPurchaseStatus = { group_id: 'g1' };

function renderPanel(props: { group?: GroupDetail; checkout?: string | null } = {}) {
  return render(
    <PlusBillingPanel
      group={props.group ?? group()}
      checkout={props.checkout}
      onEntitled={mocks.onEntitled}
    />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  intentStore.value = null;
  mocks.listPlans.mockResolvedValue(PLANS);
  mocks.getPlusPurchaseStatus.mockResolvedValue(NO_PURCHASE);
});

describe('formatPrice', () => {
  it('drops the cents on a whole amount, because $12.00 reads like a subscription row', () => {
    expect(formatPrice(1_200, 'USD')).toBe('$12');
    expect(formatPrice(1_250, 'USD')).toBe('$12.50');
  });
});

describe('isPlusRequired', () => {
  it('recognises the API’s 402 and nothing else', () => {
    expect(isPlusRequired(new ApiError(402, 'plus_required', 'Plus is required.'))).toBe(true);
    expect(isPlusRequired(new ApiError(403, 'forbidden', 'No.'))).toBe(false);
    expect(isPlusRequired(new Error('network'))).toBe(false);
  });
});

describe('the upgrade offer', () => {
  it('states the price the server configured, not one of its own', async () => {
    renderPanel();
    // $12 comes from PLANS above; nothing in the component may hardcode an amount.
    await waitFor(() => expect(screen.getByText('$12 once, for this exchange')).toBeTruthy());
    expect(screen.getByText('Upgrade this exchange — $12')).toBeTruthy();
    expect(screen.getByText(/Up to 50 participants, instead of 6\./)).toBeTruthy();
  });

  it('says it does not renew and covers this exchange only', async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/does not renew/)).toBeTruthy());
    expect(screen.getByText(/this exchange only/)).toBeTruthy();
    expect(screen.getByText(/next exchange starts on Free/)).toBeTruthy();
  });

  it('does not offer a purchase the backend has no Stripe price for', async () => {
    mocks.listPlans.mockResolvedValue(
      PLANS.map((plan) => (plan.code === 'plus' ? { ...plan, price_id: null } : plan)),
    );

    renderPanel();

    await waitFor(() => expect(screen.getByText(/Plus is not on sale yet/)).toBeTruthy());
    // The capabilities still read, because they are true; only the dead button is gone.
    expect(screen.getByText(/Up to 50 participants, instead of 6\./)).toBeTruthy();
    expect(screen.queryByText(/Upgrade this exchange/)).toBeNull();
  });

  it('tells an organizer at the Free ceiling why nobody else can join', async () => {
    renderPanel({ group: group({ members: members(6) }) });
    await waitFor(() => expect(screen.getByText(/This exchange is full/)).toBeTruthy());
    expect(screen.getByText(/Free includes 6/)).toBeTruthy();
  });
});

describe('opening Checkout', () => {
  it('remembers the intended action, then opens the session the API returned', async () => {
    mocks.createPlusCheckout.mockResolvedValue({
      checkout_url: 'https://checkout.stripe.test/session',
      session_id: 'cs_1',
      status: 'pending',
    });
    renderPanel({ group: group({ members: members(6) }) });
    await waitFor(() => expect(screen.getAllByText(/\$12/).length).toBeGreaterThan(0));

    await act(async () => {
      fireEvent.press(screen.getByText(/Upgrade this exchange/));
    });

    expect(mocks.createPlusCheckout).toHaveBeenCalledWith('token', 'g1');
    expect(WebBrowser.openBrowserAsync).toHaveBeenCalledWith('https://checkout.stripe.test/session');
    // The action is stored so the return can say "You can now …" rather than landing blank.
    expect(JSON.parse(intentStore.value as string)).toMatchObject({
      groupId: 'g1',
      action: 'invite everyone else who is waiting to join',
    });
  });

  it('forgets the intent when Checkout could not be opened at all', async () => {
    mocks.createPlusCheckout.mockRejectedValue(new Error('Plus purchasing is not configured.'));
    renderPanel();
    await waitFor(() => expect(screen.getAllByText(/\$12/).length).toBeGreaterThan(0));

    await act(async () => {
      fireEvent.press(screen.getByText(/Upgrade this exchange/));
    });

    expect(screen.getByText('Plus purchasing is not configured.')).toBeTruthy();
    expect(intentStore.value).toBeNull();
  });

  it('leaves the page entirely on the web, where Stripe redirects back itself', async () => {
    const assign = jest.fn();
    const original = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'web', configurable: true });
    Object.defineProperty(globalThis, 'location', {
      value: { assign, origin: 'https://app.humbugg.test' },
      configurable: true,
      writable: true,
    });
    mocks.createPlusCheckout.mockResolvedValue({
      checkout_url: 'https://checkout.stripe.test/session',
      session_id: 'cs_1',
      status: 'pending',
    });
    try {
      renderPanel();
      await waitFor(() => expect(screen.getAllByText(/\$12/).length).toBeGreaterThan(0));
      await act(async () => {
        fireEvent.press(screen.getByText(/Upgrade this exchange/));
      });
      expect(assign).toHaveBeenCalledWith('https://checkout.stripe.test/session');
      expect(WebBrowser.openBrowserAsync).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(Platform, 'OS', { value: original, configurable: true });
    }
  });
});

describe('coming back from Checkout', () => {
  it('says nothing was charged when the organizer cancels', async () => {
    renderPanel({ checkout: 'canceled' });
    await waitFor(() => expect(screen.getByText(/nothing was charged/)).toBeTruthy());
    expect(screen.getByText('This exchange is on Free')).toBeTruthy();
    expect(mocks.onEntitled).not.toHaveBeenCalled();
  });

  it('confirms a paid return and reads the remembered action back', async () => {
    intentStore.value = JSON.stringify({
      groupId: 'g1',
      action: 'invite everyone else who is waiting to join',
      savedAt: Date.now(),
    });
    mocks.getPlusPurchaseStatus.mockResolvedValue({
      group_id: 'g1',
      status: 'paid',
      entitlement_id: 'plus:g1',
      receipt_url: 'https://receipt.stripe.test/r1',
    });

    renderPanel({ checkout: 'success' });

    await waitFor(() =>
      expect(
        screen.getByText(
          /Payment confirmed\. That is the only charge for this exchange — nothing renews\. You can now invite everyone else who is waiting to join\./,
        ),
      ).toBeTruthy(),
    );
    expect(screen.getByText('Plus is on for this exchange')).toBeTruthy();
    expect(mocks.onEntitled).toHaveBeenCalled();
    // The intent is spent; a later visit must not replay it.
    expect(intentStore.value).toBeNull();
  });

  /**
   * The seam this whole file exists for. Stripe saying "paid" and Humbugg having APPLIED the
   * purchase are different facts: the webhook writes the entitlement and the group's plan in one
   * transaction, and `PlanCatalog.HasCapability` reads the entitlement. Announcing Plus on the
   * strength of `status === 'paid'` would promise a capability the next request answers with 402.
   */
  it('does not claim Plus on a paid purchase whose entitlement has not landed', async () => {
    mocks.getPlusPurchaseStatus.mockResolvedValue({ group_id: 'g1', status: 'paid' });

    renderPanel();

    await waitFor(() => expect(screen.getByText('This exchange is on Free')).toBeTruthy());
    expect(screen.getByText(/Plus is still being applied/)).toBeTruthy();
    expect(screen.queryByText('Plus is on for this exchange')).toBeNull();
  });

  it('says the payment is still being applied when the webhook never lands', async () => {
    jest.useFakeTimers();
    mocks.getPlusPurchaseStatus.mockResolvedValue({ group_id: 'g1', status: 'paid' });
    try {
      renderPanel({ checkout: 'success' });
      // Six tries, two seconds apart, then it stops guessing and says so.
      await act(async () => {
        await jest.advanceTimersByTimeAsync(20_000);
      });
      expect(screen.getByText(/has not finished applying it/)).toBeTruthy();
      expect(screen.queryByText('Plus is on for this exchange')).toBeNull();
      expect(mocks.onEntitled).not.toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });

  it('stops immediately on a rejected payment and says nothing is owed', async () => {
    mocks.getPlusPurchaseStatus.mockResolvedValue({ group_id: 'g1', status: 'failed' });

    renderPanel({ checkout: 'success' });

    await waitFor(() => expect(screen.getByText(/did not go through/)).toBeTruthy());
    expect(screen.getByText(/nothing is owed/)).toBeTruthy();
    expect(mocks.onEntitled).not.toHaveBeenCalled();
  });
});

describe('an exchange that already has Plus', () => {
  it('shows the receipt and repeats that it does not renew', async () => {
    mocks.getPlusPurchaseStatus.mockResolvedValue({
      group_id: 'g1',
      status: 'paid',
      entitlement_id: 'plus:g1',
      receipt_url: 'https://receipt.stripe.test/r1',
    });

    renderPanel({ group: group({ plan: 'plus' }) });

    await waitFor(() => expect(screen.getByText('Plus is on for this exchange')).toBeTruthy());
    expect(screen.getByText('View your Stripe receipt')).toBeTruthy();
    expect(screen.getByText(/does not renew, and a new exchange starts on Free/)).toBeTruthy();
    // No second sale on a paid exchange.
    expect(screen.queryByText(/Upgrade this exchange/)).toBeNull();
  });

  it('says where the receipt will come from before Stripe has sent one', async () => {
    mocks.getPlusPurchaseStatus.mockResolvedValue({
      group_id: 'g1',
      status: 'paid',
      entitlement_id: 'plus:g1',
    });

    renderPanel({ group: group({ plan: 'plus' }) });

    await waitFor(() => expect(screen.getByText(/Stripe emails the receipt/)).toBeTruthy());
  });
});

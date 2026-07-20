// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ansavva/design-system', () => ({
  Button: ({ children, ...props }: Record<string, unknown> & { children?: unknown }) => (
    <button {...(props as Record<string, unknown>)}>{children as never}</button>
  ),
  Checkbox: { Root: () => null, Indicator: () => null },
  Input: () => null,
  Textarea: () => null,
}));

vi.mock('../components/Layout', () => ({
  Card: ({ children }: { children?: unknown }) => <section>{children as never}</section>,
  Shell: ({ children }: { children?: unknown }) => <main>{children as never}</main>,
  StatusMessage: () => null,
}));

import { CheckoutRecovery, UpgradeOffer } from './GroupPage';

afterEach(() => cleanup());

describe('Plus purchase experience', () => {
  it('explains the one-time per-exchange purchase before Checkout', () => {
    render(<UpgradeOffer reason="Plus is required." busy={false} onUpgrade={() => undefined} onDismiss={() => undefined} />);

    expect(screen.getByText(/Unlock Plus for \$12/i)).toBeInTheDocument();
    expect(screen.getByText(/one payment for this exchange only/i)).toBeInTheDocument();
    expect(screen.getByText(/no subscription and no renewal/i)).toBeInTheDocument();
    expect(screen.getByText(/up to 50 total participants/i)).toBeInTheDocument();
  });

  it('shows a safe pending state until entitlement processing completes', () => {
    render(<CheckoutRecovery state="success" purchase={{ group_id: 'group-1', status: 'pending' }} intendedAction="Add participant seven." onUpgrade={() => undefined} />);

    expect(screen.getByText(/Finalizing your Plus purchase/i)).toBeInTheDocument();
    expect(screen.getByText(/securely confirming the payment/i)).toBeInTheDocument();
  });

  it('preserves the intended action and receipt after success', () => {
    render(<CheckoutRecovery state="success" purchase={{ group_id: 'group-1', status: 'paid', entitlement_id: 'plus:group-1', receipt_url: 'https://receipt.test' }} intendedAction="Add participant seven." onUpgrade={() => undefined} />);

    expect(screen.getByText(/Plus is ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Add participant seven/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view stripe receipt/i })).toHaveAttribute('href', 'https://receipt.test');
  });

  it('handles cancellation with a keyboard-accessible retry button', () => {
    const retry = vi.fn();
    render(<CheckoutRecovery state="canceled" purchase={null} intendedAction={null} onUpgrade={retry} />);

    fireEvent.click(screen.getByRole('button', { name: /return to secure checkout/i }));
    expect(retry).toHaveBeenCalledOnce();
  });
});

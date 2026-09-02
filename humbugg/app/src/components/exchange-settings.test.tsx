// The organizer's edit form (#135).
//
// The behaviours worth pinning are the two that are not obvious from looking at it: that a save
// sends back the `updated_at` it loaded with, and that a refusal is presented as "reload", not as a
// failure to retry — retrying a stale save fails identically and losing somebody else's edit is the
// thing the check exists to prevent.
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import type { GroupDetail } from '../types';

const mocks = { updateGroup: jest.fn(), onSaved: jest.fn() };

jest.mock('../api/client', () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, _code: string, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    api: { updateGroup: (...args: unknown[]) => mocks.updateGroup(...args) },
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

import { ExchangeInstructions, ExchangeSettingsPanel } from './exchange-settings';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

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
    updated_at: '2026-09-01T00:00:00Z',
    description: 'Back for another year.',
    exclusions: [],
    members: [],
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mocks.updateGroup.mockResolvedValue(group({ name: 'Renamed' }));
});

describe('editing an exchange', () => {
  it('opens with what is already saved', () => {
    render(
      <ExchangeSettingsPanel
        group={group({ instructions: 'Bring it wrapped.', spending_limit: 25 })}
        onSaved={mocks.onSaved}
      />,
    );

    expect(screen.getByLabelText('Exchange name').props.value).toBe('Office Exchange');
    expect(screen.getByLabelText('Description (optional)').props.value).toBe('Back for another year.');
    expect(screen.getByLabelText('How it works (optional)').props.value).toBe('Bring it wrapped.');
    expect(screen.getByLabelText('Spending limit in dollars (optional)').props.value).toBe('25');
  });

  /**
   * The concurrency token, sent on every save.
   *
   * This is the assertion that would catch somebody "simplifying" the request body later: the field
   * looks redundant next to the values it accompanies, and it is the only thing standing between two
   * organizers and a silently discarded edit.
   */
  it('sends back the updated_at it loaded with', async () => {
    render(<ExchangeSettingsPanel group={group()} onSaved={mocks.onSaved} />);

    fireEvent.changeText(screen.getByLabelText('Exchange name'), '  Renamed  ');
    await act(async () => {
      fireEvent.press(screen.getByText('Save changes'));
    });

    expect(mocks.updateGroup).toHaveBeenCalledWith(
      'token',
      'g1',
      expect.objectContaining({ name: 'Renamed', expected_updated_at: '2026-09-01T00:00:00Z' }),
    );
    expect(mocks.onSaved).toHaveBeenCalled();
    expect(screen.getByText('Saved.')).toBeTruthy();
  });

  it('omits the spending limit rather than sending an empty one', async () => {
    render(<ExchangeSettingsPanel group={group({ spending_limit: null })} onSaved={mocks.onSaved} />);

    await act(async () => {
      fireEvent.press(screen.getByText('Save changes'));
    });

    expect(mocks.updateGroup.mock.calls[0][2]).not.toHaveProperty('spending_limit');
  });

  /**
   * A 409 is not an ordinary error, and the copy has to say the one thing that resolves it.
   */
  it('tells you to reload when somebody else saved first', async () => {
    mocks.updateGroup.mockRejectedValue(new ApiError(409, 'conflict', 'Somebody else changed it.'));
    render(<ExchangeSettingsPanel group={group()} onSaved={mocks.onSaved} />);

    await act(async () => {
      fireEvent.press(screen.getByText('Save changes'));
    });

    expect(screen.getByText(/Reload the page to see their version/)).toBeTruthy();
    // Not reported as saved, and the caller's copy of the group is untouched.
    expect(screen.queryByText('Saved.')).toBeNull();
    expect(mocks.onSaved).not.toHaveBeenCalled();
  });

  it('will not save an exchange with no name', () => {
    render(<ExchangeSettingsPanel group={group()} onSaved={mocks.onSaved} />);

    fireEvent.changeText(screen.getByLabelText('Exchange name'), '   ');
    fireEvent.press(screen.getByText('Save changes'));

    expect(mocks.updateGroup).not.toHaveBeenCalled();
  });
});

describe('the instructions panel', () => {
  it('shows what the organizer wrote', () => {
    render(<ExchangeInstructions instructions="Bring it wrapped to the Friday lunch." />);

    expect(screen.getByText('Bring it wrapped to the Friday lunch.')).toBeTruthy();
  });

  /** A heading over nothing is worse than no heading. */
  it.each([undefined, '', '   '])('renders nothing for %p', (instructions) => {
    const { toJSON } = render(<ExchangeInstructions instructions={instructions} />);

    expect(toJSON()).toBeNull();
  });
});

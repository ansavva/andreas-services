// Gift progress (#132), on the app side.
//
// The two panels are two facts about two different gifts, owned by two different people. What is
// worth pinning is that neither control edits the other's record, and that the copy never suggests
// the organizer learns more than a count.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import type { GiftStatus } from '../types';

const mocks = {
  getGiftReceipt: jest.fn(),
  setGiftReceived: jest.fn(),
  onChange: jest.fn(),
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
      getGiftReceipt: (...args: unknown[]) => mocks.getGiftReceipt(...args),
      setGiftReceived: (...args: unknown[]) => mocks.setGiftReceived(...args),
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

import { GiftReceivedPanel, GiftStagePanel } from './gift-progress';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

function gift(overrides: Partial<GiftStatus> = {}): GiftStatus {
  return {
    stage: 'choosing',
    stage_at: null,
    received: false,
    received_at: null,
    can_change_stage: true,
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mocks.getGiftReceipt.mockResolvedValue({ received: false, received_at: null });
});

describe('the giver’s stage', () => {
  it('offers the three stages and reports the current one', () => {
    render(<GiftStagePanel gift={gift({ stage: 'purchased' })} busy={false} onChange={mocks.onChange} />);

    for (const label of ['Still choosing', 'Bought it', 'Sent it'])
      expect(screen.getByText(label)).toBeTruthy();

    fireEvent.press(screen.getByText('Sent it'));
    expect(mocks.onChange).toHaveBeenCalledWith('sent');
  });

  /** Corrections are legitimate — a returned item really does go back to choosing. */
  it('allows going backwards while the gift has not arrived', () => {
    render(<GiftStagePanel gift={gift({ stage: 'sent' })} busy={false} onChange={mocks.onChange} />);

    fireEvent.press(screen.getByText('Still choosing'));
    expect(mocks.onChange).toHaveBeenCalledWith('choosing');
  });

  /**
   * The one ordering rule that is actually true, and it is the server's — the panel only has to
   * stop offering a control the API would refuse, and say why.
   */
  it('stops offering a change once the recipient has confirmed receipt', () => {
    render(
      <GiftStagePanel
        gift={gift({ stage: 'sent', received: true, can_change_stage: false })}
        busy={false}
        onChange={mocks.onChange}
      />,
    );

    fireEvent.press(screen.getByText('Still choosing'));
    expect(mocks.onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/the stage is now fixed/)).toBeTruthy();
  });

  it('promises the organizer sees counts and nothing else', () => {
    render(<GiftStagePanel gift={gift()} busy={false} onChange={mocks.onChange} />);

    expect(screen.getByText(/never whose or what/)).toBeTruthy();
    expect(screen.getByText(/Nobody learns who you drew/)).toBeTruthy();
  });
});

describe('the recipient’s receipt', () => {
  it('confirms the gift arrived, and says the confirmation reveals nobody', async () => {
    mocks.setGiftReceived.mockResolvedValue({ received: true, received_at: '2026-12-25T00:00:00Z' });
    render(<GiftReceivedPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('My gift has arrived')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByLabelText('My gift has arrived'));
    });

    expect(mocks.setGiftReceived).toHaveBeenCalledWith('token', 'g1', true);
    expect(screen.getByText(/does not tell you, or them, who sent it/)).toBeTruthy();
  });

  it('can be taken back', async () => {
    mocks.getGiftReceipt.mockResolvedValue({ received: true, received_at: '2026-12-25T00:00:00Z' });
    mocks.setGiftReceived.mockResolvedValue({ received: false, received_at: null });
    render(<GiftReceivedPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('My gift has arrived')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByLabelText('My gift has arrived'));
    });

    expect(mocks.setGiftReceived).toHaveBeenCalledWith('token', 'g1', false);
  });

  it('reports a save that failed without pretending it worked', async () => {
    mocks.setGiftReceived.mockRejectedValue(new Error('Nope.'));
    render(<GiftReceivedPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('My gift has arrived')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByLabelText('My gift has arrived'));
    });

    expect(screen.getByText('Nope.')).toBeTruthy();
  });

  /** Sitting out, or a draw reset: there is no gift coming, and that is not a failure. */
  it.each([403, 404, 409])('renders nothing at all on %i', async (status) => {
    mocks.getGiftReceipt.mockRejectedValue(new ApiError(status, 'x', 'no'));

    const { toJSON } = render(<GiftReceivedPanel groupId="g1" />);

    await waitFor(() => expect(toJSON()).toBeNull());
  });
});

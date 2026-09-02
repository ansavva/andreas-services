// Repeating an exchange (#136).
//
// The behaviours worth pinning are the promises the panel makes in words: that nobody is added, that
// the link is shown once, and that copying last year's pair exclusions is a choice rather than a
// default. The last one matters most — "these two are a couple" may not be true a year later, and a
// constraint nobody asked for is worse than one they have to add back.
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import type { GroupDetail, RepeatedExchange } from '../types';

const mocks = { repeatExchange: jest.fn(), push: jest.fn(), setString: jest.fn() };

jest.mock('../api/client', () => ({
  api: { repeatExchange: (...args: unknown[]) => mocks.repeatExchange(...args) },
  ApiError: class extends Error {},
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('expo-router', () => ({ useRouter: () => ({ push: mocks.push }) }));

jest.mock('expo-clipboard', () => ({
  setStringAsync: (...args: unknown[]) => mocks.setString(...args),
}));

jest.mock('./shell', () => {
  const { View } = require('react-native');
  return { Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View> };
});

import { RepeatExchangePanel } from './repeat-exchange';

function group(): GroupDetail {
  return {
    group_id: 'g1',
    name: 'Office Exchange',
    status: 'drawn',
    currency: 'USD',
    plan: 'free',
    participant_limit: 6,
    is_organizer: true,
    is_owner: true,
    created_at: 'now',
    updated_at: 'now',
    description: 'Back for another year.',
    exclusions: [],
    members: [],
  };
}

const RESULT: RepeatedExchange = {
  group: { ...group(), group_id: 'g2', name: 'Office Exchange 2027', status: 'open' },
  invite_url: 'https://app.humbugg.com/join/g2#invite=secret',
  prior_participants: ['Ana', 'Robin'],
};

beforeEach(() => {
  jest.clearAllMocks();
  mocks.repeatExchange.mockResolvedValue(RESULT);
});

async function openAndCreate() {
  fireEvent.press(screen.getByText('Set up next year'));
  await act(async () => {
    fireEvent.press(screen.getByText('Create it'));
  });
}

describe('setting up next year', () => {
  it('says what does not come with it before you press anything', () => {
    render(<RepeatExchangePanel group={group()} />);

    expect(screen.getByText(/This one is left exactly as it is/)).toBeTruthy();
    expect(screen.getByText(/wishlists, addresses, messages — comes with it/)).toBeTruthy();
  });

  /**
   * Exclusions default OFF and details default ON, and the asymmetry is deliberate: a description
   * that is a year stale is a nuisance, a pair exclusion that is a year stale silently constrains a
   * draw and nobody remembers why.
   */
  it('copies the details by default and the exclusions only if asked', async () => {
    render(<RepeatExchangePanel group={group()} />);

    await openAndCreate();

    expect(mocks.repeatExchange).toHaveBeenCalledWith(
      'token',
      'g1',
      expect.objectContaining({ copy_details: true, copy_exclusions: false }),
    );
  });

  it('sends the exclusions once the organizer opts in', async () => {
    render(<RepeatExchangePanel group={group()} />);
    fireEvent.press(screen.getByText('Set up next year'));

    fireEvent.press(screen.getByLabelText('Copy the pair exclusions'));
    await act(async () => {
      fireEvent.press(screen.getByText('Create it'));
    });

    expect(mocks.repeatExchange.mock.calls[0][2]).toMatchObject({ copy_exclusions: true });
  });

  it('shows the one-time link and says nobody was added', async () => {
    render(<RepeatExchangePanel group={group()} />);

    await openAndCreate();

    expect(screen.getByText('Office Exchange 2027 is set up')).toBeTruthy();
    expect(screen.getByText(/Nobody has been added/)).toBeTruthy();
    expect(screen.getByLabelText('Invitation link for the new exchange').props.value).toBe(
      RESULT.invite_url,
    );
    // Last year's roster is a reminder of who to send to, and that is all it is.
    expect(screen.getByText('Ana, Robin')).toBeTruthy();
  });

  it('copies the link and opens the new exchange', async () => {
    render(<RepeatExchangePanel group={group()} />);
    await openAndCreate();

    fireEvent.press(screen.getByText('Copy'));
    expect(mocks.setString).toHaveBeenCalledWith(RESULT.invite_url);

    fireEvent.press(screen.getByText('Open the new exchange'));
    expect(mocks.push).toHaveBeenCalledWith('/groups/g2');
  });

  it('reports a failure instead of pretending an exchange exists', async () => {
    mocks.repeatExchange.mockRejectedValue(new Error('Complete your profile first.'));
    render(<RepeatExchangePanel group={group()} />);

    await openAndCreate();

    expect(screen.getByText('Complete your profile first.')).toBeTruthy();
    expect(screen.queryByText(/is set up/)).toBeNull();
  });

  it('will not create an exchange with no name', () => {
    render(<RepeatExchangePanel group={group()} />);
    fireEvent.press(screen.getByText('Set up next year'));

    fireEvent.changeText(screen.getByLabelText('Name the new exchange'), '   ');
    fireEvent.press(screen.getByText('Create it'));

    expect(mocks.repeatExchange).not.toHaveBeenCalled();
  });
});

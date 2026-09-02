// The organizer readiness dashboard (#133).
//
// The behaviours worth pinning are the ones a screenshot cannot check: that the screen never
// re-derives readiness (it renders the state the API sent, even an unexpected one), that a
// participant who follows the URL is told why they cannot see it, that a long roster stays
// complete, and that each row carries one sentence for a screen reader instead of three loose chips.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mocks = {
  push: jest.fn(),
  getGroup: jest.fn(),
  getReadiness: jest.fn(),
  updateGroup: jest.fn(),
  listPlans: jest.fn(),
  getPlusPurchaseStatus: jest.fn(),
  listInvitations: jest.fn(),
  createInvitations: jest.fn(),
  resendInvitation: jest.fn(),
  revokeInvitation: jest.fn(),
  setOrganizerRole: jest.fn(),
  getReminders: jest.fn(),
  updateReminders: jest.fn(),
  updateCustomization: jest.fn(),
  width: 1280,
};

jest.mock('expo-router', () => {
  const { Text } = require('react-native');
  return {
    useRouter: () => ({ push: mocks.push }),
    Link: ({ children }: { children?: React.ReactNode }) => <Text>{children}</Text>,
  };
});

// The error class is declared INSIDE the factory. Babel hoists `import ... from './organize'`
// above a top-level class declaration, so a class defined out here is still in its temporal dead
// zone when the factory runs, and the screen's `err instanceof ApiError` throws on `undefined`
// instead of branching. `jest.requireMock` below is how a test gets hold of the same class.
jest.mock('../api/client', () => {
  // Plain assignment, not a TypeScript parameter property: the out-of-scope guard reads the
  // desugared `this.status = status` as a free variable and rejects the whole factory.
  class ApiError extends Error {
    status: number;
    constructor(status: number, _code: string, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    api: {
      getGroup: (...args: unknown[]) => mocks.getGroup(...args),
      getReadiness: (...args: unknown[]) => mocks.getReadiness(...args),
      updateGroup: (...args: unknown[]) => mocks.updateGroup(...args),
      listPlans: (...args: unknown[]) => mocks.listPlans(...args),
      getPlusPurchaseStatus: (...args: unknown[]) => mocks.getPlusPurchaseStatus(...args),
      listInvitations: (...args: unknown[]) => mocks.listInvitations(...args),
      createInvitations: (...args: unknown[]) => mocks.createInvitations(...args),
      resendInvitation: (...args: unknown[]) => mocks.resendInvitation(...args),
      revokeInvitation: (...args: unknown[]) => mocks.revokeInvitation(...args),
      setOrganizerRole: (...args: unknown[]) => mocks.setOrganizerRole(...args),
      getReminders: (...args: unknown[]) => mocks.getReminders(...args),
      updateReminders: (...args: unknown[]) => mocks.updateReminders(...args),
      updateCustomization: (...args: unknown[]) => mocks.updateCustomization(...args),
    },
    ApiError,
  };
});

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('../components/shell', () => {
  const { Text, View } = require('react-native');
  return {
    Shell: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    // Wraps in Text like the real one — a bare string under a View is not a text host, and
    // getByText would not find it.
    LoadingPanel: ({ children }: { children?: React.ReactNode }) => <Text>{children}</Text>,
  };
});

// The one seam the layout tests need: a phone is a narrow window, not a different renderer.
jest.mock('react-native/Libraries/Utilities/useWindowDimensions', () => ({
  __esModule: true,
  default: () => ({ width: mocks.width, height: 800, scale: 2, fontScale: 1 }),
}));

import OrganizeScreen from './organize';
import type {
  GroupReadiness,
  ParticipantReadiness,
  ReminderOverview,
  ReminderSettings,
} from '../types';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

const participant = (
  name: string,
  overrides: Partial<ParticipantReadiness> = {},
): ParticipantReadiness => ({
  member_id: `member-${name}`,
  display_name: name,
  role: 'participant',
  is_participating: true,
  wishlist: 'ready',
  wish_count: 3,
  has_general_preferences: true,
  address: 'not_required',
  assignment: 'not_applicable',
  nudges: [],
  ...overrides,
});

const readiness = (overrides: Partial<GroupReadiness> = {}): GroupReadiness => {
  const participants = overrides.participants ?? [participant('Alex', { role: 'owner' })];
  const participating = participants.filter((person) => person.is_participating).length;
  return {
    group_id: 'group-1',
    status: 'open',
    plan: 'free',
    requires_address: false,
    participants,
    pending_invitations: [],
    gift_progress: null,
    ...overrides,
    counts: {
      members: participants.length,
      participating,
      not_participating: participants.length - participating,
      pending_invitations: overrides.pending_invitations?.length ?? 0,
      wishlist_ready: participants.filter((p) => p.wishlist === 'ready').length,
      address_ready: participants.filter((p) => p.address === 'ready').length,
      assignments_viewed: participants.filter((p) => p.assignment === 'ready').length,
      needs_nudge:
        participants.filter((p) => p.nudges.length > 0).length +
        (overrides.pending_invitations?.length ?? 0),
      ...overrides.counts,
    },
  };
};

beforeEach(() => {
  jest.clearAllMocks();
  mocks.width = 1280;
  mocks.getGroup.mockResolvedValue({
    group_id: 'group-1',
    name: 'Office Secret Santa',
    plan: 'plus',
    is_owner: true,
  });
  mocks.getReadiness.mockResolvedValue(readiness());
  mocks.updateGroup.mockResolvedValue({});
  mocks.listPlans.mockResolvedValue([
    { code: 'free', name: 'Free', participant_limit: 6, marketed_as_unlimited: false, price_cents: 0, currency: 'USD', billing_cadence: 'free' },
    { code: 'plus', name: 'Plus', participant_limit: 50, marketed_as_unlimited: false, price_cents: 1_200, currency: 'USD', billing_cadence: 'one_time', price_id: 'price_plus' },
  ]);
  mocks.getPlusPurchaseStatus.mockResolvedValue({ group_id: 'group-1' });
  mocks.listInvitations.mockResolvedValue([]);
  mocks.createInvitations.mockResolvedValue({ invitations: [] });
  mocks.resendInvitation.mockResolvedValue({});
  mocks.revokeInvitation.mockResolvedValue(undefined);
  mocks.setOrganizerRole.mockResolvedValue({});
  mocks.getReminders.mockResolvedValue(reminders());
  mocks.updateReminders.mockImplementation((_t: string, _g: string, settings: object) =>
    Promise.resolve(reminders(settings as Partial<ReminderSettings>)),
  );
  mocks.updateCustomization.mockResolvedValue({
    group_id: 'group-1',
    name: 'Office Secret Santa',
    plan: 'plus',
    is_owner: true,
    customization: {
      greeting: 'Welcome',
      instructions: '',
      primary_color: '#7C2D12',
      accent_color: '#F59E0B',
      image_data_url: null,
    },
  });
});

const reminders = (settings: Partial<ReminderSettings> = {}): ReminderOverview => ({
  settings: {
    state: 'stopped',
    remind_unaccepted_invitations: true,
    remind_incomplete_readiness: false,
    interval_days: 3,
    quiet_start_utc_hour: 9,
    quiet_end_utc_hour: 21,
    ...settings,
  },
  next_scheduled_at: null,
  recent_history: [],
});

describe('loading and failure', () => {
  it('holds a loading state until both calls resolve', async () => {
    let release: (value: unknown) => void = () => {};
    mocks.getReadiness.mockReturnValue(new Promise((resolve) => { release = resolve; }));

    render(<OrganizeScreen groupId="group-1" />);
    expect(screen.getByText('Checking who is ready…')).toBeOnTheScreen();

    release(readiness());
    await waitFor(() => expect(screen.getByText('Who is ready')).toBeOnTheScreen());
  });

  it('tells a participant why the dashboard is closed to them rather than showing nothing', async () => {
    mocks.getReadiness.mockRejectedValue(new ApiError(403, 'forbidden', 'nope'));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(
        screen.getByText('Only an organizer of this exchange can see its readiness dashboard.'),
      ).toBeOnTheScreen(),
    );
  });

  it('surfaces any other failure with the message the API gave', async () => {
    mocks.getReadiness.mockRejectedValue(new Error('The exchange is on fire.'));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('The exchange is on fire.')).toBeOnTheScreen());
  });
});

describe('the empty and settled states', () => {
  it('says nobody has joined instead of drawing an empty roster', async () => {
    mocks.getReadiness.mockResolvedValue(readiness({ participants: [] }));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByText('Nobody has joined yet. Share the invitation link.')).toBeOnTheScreen(),
    );
  });

  it('says nobody needs chasing when nobody does', async () => {
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Nobody — everyone is ready')).toBeOnTheScreen());
    expect(screen.getByText('Every participant has done what the exchange asks.')).toBeOnTheScreen();
  });
});

describe('the nudge list', () => {
  it('names each person once with every reason they are being chased', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        status: 'drawn',
        requires_address: true,
        participants: [
          participant('Alex', { role: 'owner', address: 'ready', assignment: 'ready' }),
          participant('Sam', {
            wishlist: 'missing',
            wish_count: 0,
            address: 'missing',
            assignment: 'missing',
            nudges: ['no_wishlist', 'no_address', 'assignment_not_viewed'],
          }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('1 to chase')).toBeOnTheScreen());
    expect(
      screen.getByText(
        'Has not written a wishlist · Has not given a mailing address · Has not opened their match',
      ),
    ).toBeOnTheScreen();
  });

  it('calls out a bounced invitation as an address problem, not a slow reply', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        pending_invitations: [
          {
            invitation_id: 'i-1',
            email: 'nobody@example.com',
            status: 'bounced',
            expires_at: '2026-12-01T00:00:00Z',
          },
          {
            invitation_id: 'i-2',
            email: 'slow@example.com',
            status: 'sent',
            expires_at: '2026-12-01T00:00:00Z',
          },
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByText('Their invitation bounced — check the address')).toBeOnTheScreen(),
    );
    expect(screen.getByText('Has not accepted their invitation')).toBeOnTheScreen();
  });
});

describe('what the roster shows', () => {
  it('renders the state the server sent and does not recompute it from the wish count', async () => {
    // Deliberately contradictory: three wishes and a "missing" verdict. The server decides; if this
    // screen ever starts inferring readiness from wish_count, this test is what catches it.
    mocks.getReadiness.mockResolvedValue(
      readiness({
        participants: [participant('Sam', { wishlist: 'missing', wish_count: 3, nudges: ['no_wishlist'] })],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('No wishlist')).toBeOnTheScreen());
    expect(screen.queryByText('3 wishes')).toBeNull();
  });

  it('counts a single wish in the singular', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({ participants: [participant('Sam', { wish_count: 1 })] }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('1 wish')).toBeOnTheScreen());
  });

  it('hides the address and assignment chips the exchange is not asking about', async () => {
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('3 wishes')).toBeOnTheScreen());
    expect(screen.queryByText('Address not needed')).toBeNull();
    // "Before the draw" appears once, as the Matches-opened tile's value — never as a row chip.
    expect(screen.getAllByText('Before the draw')).toHaveLength(1);
  });

  it('shows a match chip once the draw has happened', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        status: 'drawn',
        participants: [
          participant('Alex', { assignment: 'ready' }),
          participant('Sam', { assignment: 'missing', nudges: ['assignment_not_viewed'] }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Opened their match')).toBeOnTheScreen());
    expect(screen.getByText('Has not looked yet')).toBeOnTheScreen();
  });

  it('asks nothing of somebody sitting the exchange out', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        participants: [
          participant('Alex'),
          participant('Sam', {
            is_participating: false,
            wishlist: 'not_applicable',
            address: 'not_applicable',
            assignment: 'not_applicable',
            wish_count: 0,
          }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Participant · Sitting out')).toBeOnTheScreen());
    expect(screen.getByText('1 sitting out')).toBeOnTheScreen();
  });

  it('keeps a long roster complete rather than truncating it', async () => {
    const many = Array.from({ length: 120 }, (_, index) =>
      participant(`Person ${String(index).padStart(3, '0')}`, {
        member_id: `member-${index}`,
        wishlist: index % 3 === 0 ? 'missing' : 'ready',
        wish_count: index % 3 === 0 ? 0 : 2,
        nudges: index % 3 === 0 ? ['no_wishlist'] : [],
      }),
    );
    mocks.getReadiness.mockResolvedValue(readiness({ participants: many }));

    render(<OrganizeScreen groupId="group-1" />);

    // Person 000 has no list, so they are named twice — once to chase, once in the roster.
    await waitFor(() => expect(screen.getAllByText('Person 000')).toHaveLength(2));
    expect(screen.getByText('Person 119')).toBeOnTheScreen();
    // 40 of the 120 are missing a list; the roll-up and the nudge panel must agree on that.
    expect(screen.getByText('40 to chase')).toBeOnTheScreen();
    expect(screen.getByText('80 of 120')).toBeOnTheScreen();
  });
});

describe('the address setting', () => {
  it('saves the switch and reloads, so the counts follow the setting', async () => {
    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Not needed')).toBeOnTheScreen());

    mocks.getReadiness.mockResolvedValue(
      readiness({ requires_address: true, participants: [participant('Alex', { address: 'missing', nudges: ['no_address'] })] }),
    );
    fireEvent.press(screen.getByLabelText('Gifts are posted to a mailing address'));

    await waitFor(() =>
      expect(mocks.updateGroup).toHaveBeenCalledWith('token', 'group-1', { requires_address: true }),
    );
    await waitFor(() => expect(screen.getByText('No address')).toBeOnTheScreen());
  });

  it('reports a failed save without pretending the setting changed', async () => {
    mocks.updateGroup.mockRejectedValue(new Error('Nope.'));

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => screen.getByLabelText('Gifts are posted to a mailing address'));
    fireEvent.press(screen.getByLabelText('Gifts are posted to a mailing address'));

    await waitFor(() => expect(screen.getByText('Nope.')).toBeOnTheScreen());
    expect(screen.getByText('Not needed')).toBeOnTheScreen();
  });
});

describe('gift progress', () => {
  it('says gift progress is not tracked rather than reporting zero of everything', async () => {
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Nothing to track yet.')).toBeOnTheScreen());
    expect(screen.queryByText('0 of 1')).toBeNull();
  });

  it('renders the counts once the API sends them', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({ gift_progress: { purchased: 4, sent: 2, received: 1, total: 5 } }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('4 of 5')).toBeOnTheScreen());
    expect(screen.getByText('2 of 5')).toBeOnTheScreen();
    expect(screen.getByText('1 of 5')).toBeOnTheScreen();
    expect(screen.queryByText('Nothing to track yet.')).toBeNull();
  });
});

describe('mobile and assistive technology', () => {
  it('renders the whole dashboard at a 390px phone width', async () => {
    mocks.width = 390;
    mocks.getReadiness.mockResolvedValue(
      readiness({
        status: 'drawn',
        requires_address: true,
        participants: [
          participant('Alex', { role: 'owner', address: 'ready', assignment: 'ready' }),
          participant('Sam', { address: 'missing', assignment: 'missing', nudges: ['no_address', 'assignment_not_viewed'] }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Who is ready')).toBeOnTheScreen());
    // Every tile, chip and row survives the narrow layout — the columns change, the content does not.
    expect(screen.getByText('Taking part')).toBeOnTheScreen();
    expect(screen.getByText('Matches opened')).toBeOnTheScreen();
    expect(screen.getByText('No address')).toBeOnTheScreen();
    expect(screen.getByText('Has not looked yet')).toBeOnTheScreen();
  });

  it('gives every participant row one sentence rather than three loose chips', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        status: 'drawn',
        requires_address: true,
        participants: [
          participant('Sam', {
            wishlist: 'missing',
            wish_count: 0,
            address: 'ready',
            assignment: 'missing',
            nudges: ['no_wishlist', 'assignment_not_viewed'],
          }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(
        screen.getByLabelText('Sam, Participant, No wishlist, Address on file, Has not looked yet'),
      ).toBeOnTheScreen(),
    );
  });

  it('says who is not participating in that same sentence, and stops there', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        participants: [
          participant('Sam', {
            is_participating: false,
            wishlist: 'not_applicable',
            address: 'not_applicable',
            assignment: 'not_applicable',
          }),
        ],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByLabelText('Sam, Participant, not participating')).toBeOnTheScreen(),
    );
  });

  it('gives each meter a label that reads as a fraction', async () => {
    mocks.getReadiness.mockResolvedValue(
      readiness({
        participants: [participant('Alex'), participant('Sam', { wishlist: 'missing', wish_count: 0, nudges: ['no_wishlist'] })],
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByLabelText('Wishlists: 1 of 2')).toBeOnTheScreen());
  });
});

// The billing area (#141) belongs to the person who can actually be charged. `GET
// .../billing/plus` refuses anyone but the owner, so rendering it for a co-organizer would show a
// panel whose only possible content is its own 403.
describe('the billing area', () => {
  const owned = {
    group_id: 'group-1',
    name: 'Office Secret Santa',
    plan: 'free',
    participant_limit: 6,
    is_owner: true,
    is_organizer: true,
    members: [{ member_id: 'm1', display_name: 'Ana', is_organizer: true, is_participating: true }],
  };

  it('offers Plus to the owner', async () => {
    mocks.getGroup.mockResolvedValue(owned);
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('This exchange is on Free')).toBeTruthy());
    expect(screen.getByText('Upgrade this exchange — $12')).toBeTruthy();
  });

  // A confirmed purchase re-reads the group so the plan chip follows — QUIETLY. A loud reload
  // swaps this screen for its loading panel, which unmounts the billing panel; Stripe's
  // `?checkout=success` is still in the URL, so the remount confirms again, entitles again and
  // reloads again. This asserts the reload is bounded.
  it('does not reload itself in a loop when a paid return lands', async () => {
    mocks.getGroup.mockResolvedValue(owned);
    mocks.getPlusPurchaseStatus.mockResolvedValue({
      group_id: 'group-1',
      status: 'paid',
      entitlement_id: 'plus:group-1',
    });

    render(<OrganizeScreen groupId="group-1" checkout="success" />);

    await waitFor(() => expect(screen.getByText('Plus is on for this exchange')).toBeTruthy());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    // One mount read, one after the entitlement. Anything more is the loop.
    expect(mocks.getGroup.mock.calls.length).toBeLessThanOrEqual(2);
  });

  it('shows a co-organizer nothing about billing', async () => {
    mocks.getGroup.mockResolvedValue({ ...owned, is_owner: false });
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getByText('Who is ready')).toBeTruthy());
    expect(screen.queryByText('This exchange is on Free')).toBeNull();
    expect(mocks.getPlusPurchaseStatus).not.toHaveBeenCalled();
  });
});

// ─── Managed invitations and co-organizers (#574) ───────────────────────────────────────────────
//
// Both capabilities shipped complete on the backend in August 2026 and were reachable from no
// screen until now, so what these pin is the wiring: that the endpoint is actually called, that a
// Free exchange is told what it is missing rather than shown a button that only ever fails, and
// that the two refusals land in the right places.

describe('managed invitations', () => {
  it('sends what was pasted, however it was separated', async () => {
    mocks.createInvitations.mockResolvedValue({
      invitations: [
        { invitation_id: 'i1', email: 'robin@example.com', status: 'sent', expires_at: '2026-10-01T00:00:00Z' },
        { invitation_id: 'i2', email: 'sam@example.com', status: 'sent', expires_at: '2026-10-01T00:00:00Z' },
      ],
    });

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Invite people by email')).toBeOnTheScreen());

    fireEvent.changeText(
      screen.getByLabelText('Email addresses'),
      'robin@example.com, sam@example.com\n',
    );
    // The button counts them, which is the only feedback before the send that the paste parsed.
    fireEvent.press(await screen.findByText('Send 2 invitations'));

    await waitFor(() =>
      expect(mocks.createInvitations).toHaveBeenCalledWith('token', 'group-1', [
        'robin@example.com',
        'sam@example.com',
      ]),
    );
    await waitFor(() => expect(screen.getByText('2 invitations sent.')).toBeOnTheScreen());
  });

  it('drops a repeated address rather than letting the server refuse the whole batch', async () => {
    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Invite people by email')).toBeOnTheScreen());

    fireEvent.changeText(
      screen.getByLabelText('Email addresses'),
      'robin@example.com\nROBIN@example.com',
    );
    fireEvent.press(await screen.findByText('Send the invitation'));

    await waitFor(() =>
      expect(mocks.createInvitations).toHaveBeenCalledWith('token', 'group-1', ['robin@example.com']),
    );
  });

  it('shows the server’s own words when an address is refused', async () => {
    mocks.createInvitations.mockRejectedValue(
      new Error("'not-an-address' is not a valid single email address."),
    );

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Invite people by email')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('Email addresses'), 'not-an-address');
    fireEvent.press(await screen.findByText('Send the invitation'));

    await waitFor(() =>
      expect(
        screen.getByText("'not-an-address' is not a valid single email address."),
      ).toBeOnTheScreen(),
    );
  });

  it('offers Plus instead of a form when the exchange is on Free', async () => {
    mocks.listInvitations.mockRejectedValue(new ApiError(402, 'plus_required', 'Plus required.'));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByText('Sending and tracking invitations is part of Plus.')).toBeOnTheScreen(),
    );
    expect(screen.queryByLabelText('Email addresses')).toBeNull();
  });

  it('lets an outstanding invitation be sent again or withdrawn, and a joined one neither', async () => {
    mocks.listInvitations.mockResolvedValue([
      { invitation_id: 'i1', email: 'robin@example.com', status: 'sent', expires_at: '2026-10-01T00:00:00Z' },
      { invitation_id: 'i2', email: 'sam@example.com', status: 'accepted', expires_at: '2026-10-01T00:00:00Z', accepted_at: '2026-09-01T00:00:00Z' },
    ]);

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('robin@example.com')).toBeOnTheScreen());

    // One row is actionable, the other is history — so exactly one of each button exists.
    expect(screen.getAllByText('Send again')).toHaveLength(1);
    expect(screen.getAllByText('Withdraw')).toHaveLength(1);
    expect(screen.getByText('Joined')).toBeOnTheScreen();

    fireEvent.press(screen.getByText('Withdraw'));
    await waitFor(() =>
      expect(mocks.revokeInvitation).toHaveBeenCalledWith('token', 'group-1', 'i1'),
    );
  });

  it('explains a resend that came too soon rather than looking like nothing happened', async () => {
    mocks.listInvitations.mockResolvedValue([
      { invitation_id: 'i1', email: 'robin@example.com', status: 'sent', expires_at: '2026-10-01T00:00:00Z' },
    ]);
    mocks.resendInvitation.mockRejectedValue(new Error('Wait 15 minutes before resending.'));

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('robin@example.com')).toBeOnTheScreen());

    fireEvent.press(screen.getByText('Send again'));

    await waitFor(() =>
      expect(screen.getByText('Wait 15 minutes before resending.')).toBeOnTheScreen(),
    );
  });
});

describe('co-organizers', () => {
  const roster = [
    participant('Alex', { role: 'owner' }),
    participant('Robin'),
    participant('Sam', { role: 'co_organizer' }),
  ];

  it('promotes and demotes from the roster', async () => {
    mocks.getReadiness.mockResolvedValue(readiness({ participants: roster }));

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('The full roster')).toBeOnTheScreen());

    // The owner has no button at all: the backend refuses to demote them, so offering it would be
    // a button whose only outcome is a 409.
    expect(screen.getAllByText('Make organizer')).toHaveLength(1);
    expect(screen.getAllByText('Remove as organizer')).toHaveLength(1);

    fireEvent.press(screen.getByText('Make organizer'));
    await waitFor(() =>
      expect(mocks.setOrganizerRole).toHaveBeenCalledWith('token', 'group-1', 'member-Robin', true),
    );

    fireEvent.press(screen.getByText('Remove as organizer'));
    await waitFor(() =>
      expect(mocks.setOrganizerRole).toHaveBeenCalledWith('token', 'group-1', 'member-Sam', false),
    );
  });

  it('shows a co-organizer no role buttons, because the backend is owner-only', async () => {
    mocks.getGroup.mockResolvedValue({
      group_id: 'group-1',
      name: 'Office Secret Santa',
      plan: 'plus',
      is_owner: false,
    });
    mocks.getReadiness.mockResolvedValue(readiness({ participants: roster }));

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('The full roster')).toBeOnTheScreen());

    expect(screen.queryByText('Make organizer')).toBeNull();
    expect(screen.queryByText('Remove as organizer')).toBeNull();
  });

  it('offers Plus only once the owner has actually tried', async () => {
    mocks.getReadiness.mockResolvedValue(readiness({ participants: roster }));
    mocks.setOrganizerRole.mockRejectedValue(new ApiError(402, 'plus_required', 'Plus required.'));

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('The full roster')).toBeOnTheScreen());

    // An upgrade offer above an untouched roster is an advert, not an answer.
    expect(screen.queryByText('Sharing the organizing is part of Plus.')).toBeNull();

    fireEvent.press(screen.getByText('Make organizer'));

    await waitFor(() =>
      expect(screen.getByText('Sharing the organizing is part of Plus.')).toBeOnTheScreen(),
    );
  });
});

// ─── Reminders and customization (#574) ─────────────────────────────────────────────────────────

describe('scheduled reminders', () => {
  it('says in one sentence what is about to happen, and to whom', async () => {
    mocks.getReminders.mockResolvedValue(
      reminders({
        state: 'active',
        remind_unaccepted_invitations: true,
        remind_incomplete_readiness: true,
        interval_days: 3,
      }),
    );

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(
        screen.getAllByText(
          'Reminds people who have not accepted their invitation and people whose list or address is not finished, every 3 days, between 09:00–21:00 UTC.',
        ).length,
      ).toBeGreaterThan(0),
    );
  });

  it('says nothing is sent when it is off, rather than describing a schedule that will not run', async () => {
    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() => expect(screen.getAllByText('Nothing is sent.').length).toBeGreaterThan(0));
  });

  it('saves the settings and re-describes what it will now do', async () => {
    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Chasing, without you doing it')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('How often, in days'), '7');
    fireEvent.press(screen.getByText('Save reminder settings'));

    await waitFor(() =>
      expect(mocks.updateReminders).toHaveBeenCalledWith(
        'token',
        'group-1',
        expect.objectContaining({ interval_days: 7 }),
      ),
    );
  });

  it('shows the server’s refusal rather than saving nothing quietly', async () => {
    mocks.updateReminders.mockRejectedValue(
      new Error('Reminder interval must be between 1 and 14 days.'),
    );

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('Chasing, without you doing it')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('How often, in days'), '90');
    fireEvent.press(screen.getByText('Save reminder settings'));

    await waitFor(() =>
      expect(
        screen.getByText('Reminder interval must be between 1 and 14 days.'),
      ).toBeOnTheScreen(),
    );
  });

  it('offers Plus instead of settings on a Free exchange', async () => {
    mocks.getReminders.mockRejectedValue(new ApiError(402, 'plus_required', 'Plus required.'));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByText('Automatic reminders are part of Plus.')).toBeOnTheScreen(),
    );
    expect(screen.queryByLabelText('How often, in days')).toBeNull();
  });

  // The bug this pins shipped once: the catch set an error and the guard under it returned null,
  // so a failed first read rendered NOTHING — no settings, no error, no panel.
  it('says why it could not load, instead of being absent', async () => {
    mocks.getReminders.mockRejectedValue(new Error('The reminder service is down.'));

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(screen.getByText('The reminder service is down.')).toBeOnTheScreen(),
    );
  });
});

describe('exchange customization', () => {
  it('sends the greeting on the field name the API takes', async () => {
    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('How this exchange looks')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('Greeting'), 'Welcome to the Holly Jolly Crew');
    fireEvent.press(screen.getByText('Save how it looks'));

    // `image`, not `image_data_url`. The response uses the other name, and sending it back saves
    // nothing while looking exactly like a picker that failed.
    await waitFor(() =>
      expect(mocks.updateCustomization).toHaveBeenCalledWith('token', 'group-1', {
        greeting: 'Welcome to the Holly Jolly Crew',
        instructions: '',
        primary_color: '#7C2D12',
        accent_color: '#F59E0B',
        image: '',
      }),
    );
  });

  it('shows the server’s wording when it refuses markup', async () => {
    mocks.updateCustomization.mockRejectedValue(
      new Error('greeting cannot contain HTML or links.'),
    );

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('How this exchange looks')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('Greeting'), '<b>hi</b>');
    fireEvent.press(screen.getByText('Save how it looks'));

    await waitFor(() =>
      expect(screen.getByText('greeting cannot contain HTML or links.')).toBeOnTheScreen(),
    );
  });

  it('says a half-typed colour is not one yet, rather than painting a swatch of nothing', async () => {
    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('How this exchange looks')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('Main colour'), '#7C2D');

    await waitFor(() => expect(screen.getByText('Not a colour yet')).toBeOnTheScreen());
  });

  // Unlike invitations and reminders there is no read to be refused — customization is a PUT — so
  // a Free organizer would otherwise be given a whole form that can only fail on save.
  it('offers Plus instead of the form on a Free exchange, before anything is typed', async () => {
    mocks.getGroup.mockResolvedValue({
      group_id: 'group-1',
      name: 'Office Secret Santa',
      plan: 'free',
      participant_limit: 6,
      is_owner: true,
      is_organizer: true,
      members: [{ member_id: 'm1', display_name: 'Ana', is_organizer: true, is_participating: true }],
    });

    render(<OrganizeScreen groupId="group-1" />);

    await waitFor(() =>
      expect(
        screen.getByText('Your own greeting, instructions and colours are part of Plus.'),
      ).toBeOnTheScreen(),
    );
    expect(screen.queryByLabelText('Greeting')).toBeNull();
  });

  it('still takes a 402 on save as the answer, if the plan changed underneath', async () => {
    mocks.updateCustomization.mockRejectedValue(
      new ApiError(402, 'plus_required', 'Plus required.'),
    );

    render(<OrganizeScreen groupId="group-1" />);
    await waitFor(() => expect(screen.getByText('How this exchange looks')).toBeOnTheScreen());
    fireEvent.press(screen.getByText('Save how it looks'));

    await waitFor(() =>
      expect(
        screen.getByText('Your own greeting, instructions and colours are part of Plus.'),
      ).toBeOnTheScreen(),
    );
  });
});

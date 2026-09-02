// The wishlist editor. Covers the interactions someone actually performs on their own list, and the
// two rules that matter beyond the UI: a reorder sends a complete order, and the giver's view is
// read-only.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import type { RecipientWish, Wish } from '../types';

const mocks = {
  listWishes: jest.fn(),
  createWish: jest.fn(),
  updateWish: jest.fn(),
  deleteWish: jest.fn(),
  reorderWishes: jest.fn(),
};

jest.mock('../api/client', () => ({
  api: {
    listWishes: (...args: unknown[]) => mocks.listWishes(...args),
    createWish: (...args: unknown[]) => mocks.createWish(...args),
    updateWish: (...args: unknown[]) => mocks.updateWish(...args),
    deleteWish: (...args: unknown[]) => mocks.deleteWish(...args),
    reorderWishes: (...args: unknown[]) => mocks.reorderWishes(...args),
  },
  ApiError: class extends Error {},
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('./shell', () => {
  const { View } = require('react-native');
  return { Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View> };
});

import { RecipientWishList, WishListPanel } from './wishlist';

function wish(overrides: Partial<Wish> & { wish_id: string; title: string }): Wish {
  return {
    kind: 'product',
    url: null,
    image_url: null,
    price_cents: null,
    currency: null,
    quantity: 1,
    priority: 'normal',
    details: null,
    position: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mocks.listWishes.mockResolvedValue([]);
  mocks.createWish.mockResolvedValue({});
  mocks.updateWish.mockResolvedValue({});
  mocks.deleteWish.mockResolvedValue({});
  mocks.reorderWishes.mockResolvedValue([]);
});

describe('the empty and loaded states', () => {
  it('invites a first wish when the list is empty', async () => {
    render(<WishListPanel groupId="g1" />);

    expect(await screen.findByText('Nothing on your list yet')).toBeTruthy();
  });

  it('surfaces a load failure rather than showing an empty list', async () => {
    mocks.listWishes.mockRejectedValue(new Error('Network unavailable'));

    render(<WishListPanel groupId="g1" />);

    expect(await screen.findByText('Network unavailable')).toBeTruthy();
    expect(screen.queryByText('Nothing on your list yet')).toBeNull();
  });

  it('lists the wishes it loaded', async () => {
    mocks.listWishes.mockResolvedValue([
      wish({ wish_id: 'a', title: 'Chef knife', position: 0 }),
      wish({ wish_id: 'b', title: 'Cycling gloves', position: 1 }),
    ]);

    render(<WishListPanel groupId="g1" />);

    expect(await screen.findByText('Chef knife')).toBeTruthy();
    expect(screen.getByText('Cycling gloves')).toBeTruthy();
  });
});

describe('adding a wish', () => {
  it('sends the trimmed values and reloads', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), '  Chef knife  ');
    fireEvent.press(screen.getByText('Add to my list'));

    await waitFor(() => expect(mocks.createWish).toHaveBeenCalled());
    expect(mocks.createWish.mock.calls[0][2]).toMatchObject({ title: 'Chef knife', quantity: 1 });
    expect(mocks.listWishes).toHaveBeenCalledTimes(2);
  });

  // Optional fields left untouched are absent rather than empty, so the server is not asked to
  // store a blank URL for every wish anyone ever adds.
  it('omits optional fields the person never filled in', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Chef knife');
    fireEvent.press(screen.getByText('Add to my list'));

    await waitFor(() => expect(mocks.createWish).toHaveBeenCalled());
    const payload = mocks.createWish.mock.calls[0][2];
    expect(payload).not.toHaveProperty('url');
    expect(payload).not.toHaveProperty('price_cents');
    expect(payload).not.toHaveProperty('details');
  });

  it('refuses a wish with no name without calling the API', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.press(screen.getByText('Add to my list'));

    expect(await screen.findByText('Give the wish a name.')).toBeTruthy();
    expect(mocks.createWish).not.toHaveBeenCalled();
  });

  it('refuses a link that is not a complete web address', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Chef knife');
    fireEvent.changeText(screen.getByLabelText('Link (optional)'), 'javascript:alert(1)');
    fireEvent.press(screen.getByText('Add to my list'));

    expect(await screen.findByText('The link must start with http:// or https://.')).toBeTruthy();
    expect(mocks.createWish).not.toHaveBeenCalled();
  });

  it('refuses a price that is not a number', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Chef knife');
    fireEvent.changeText(screen.getByLabelText('Rough price (optional)'), 'about twenty');
    fireEvent.press(screen.getByText('Add to my list'));

    expect(await screen.findByText(/Price must be a number/)).toBeTruthy();
    expect(mocks.createWish).not.toHaveBeenCalled();
  });

  it('converts a decimal price to minor units', async () => {
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Chef knife');
    fireEvent.changeText(screen.getByLabelText('Rough price (optional)'), '25.99');
    fireEvent.press(screen.getByText('Add to my list'));

    await waitFor(() => expect(mocks.createWish).toHaveBeenCalled());
    expect(mocks.createWish.mock.calls[0][2]).toMatchObject({ price_cents: 2599 });
  });

  it('keeps the form open and reports the failure when the save fails', async () => {
    mocks.createWish.mockRejectedValue(new Error('Wishlist is full'));
    render(<WishListPanel groupId="g1" />);
    fireEvent.press(await screen.findByText('Add a wish'));

    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Chef knife');
    fireEvent.press(screen.getByText('Add to my list'));

    expect(await screen.findByText('Wishlist is full')).toBeTruthy();
    expect(screen.getByText('Add to my list')).toBeTruthy();
  });
});

describe('reordering', () => {
  // The API rejects a partial order, so the UI has to send the whole list every time. Sending only
  // the moved pair would leave every other wish at a stale position.
  it('sends the complete new order, not just the moved wish', async () => {
    mocks.listWishes.mockResolvedValue([
      wish({ wish_id: 'a', title: 'Chef knife', position: 0 }),
      wish({ wish_id: 'b', title: 'Cycling gloves', position: 1 }),
      wish({ wish_id: 'c', title: 'Coffee grinder', position: 2 }),
    ]);
    render(<WishListPanel groupId="g1" />);

    fireEvent.press(await screen.findByLabelText('Move Coffee grinder up'));

    await waitFor(() => expect(mocks.reorderWishes).toHaveBeenCalled());
    expect(mocks.reorderWishes.mock.calls[0][2]).toEqual(['a', 'c', 'b']);
  });

  it('does not offer to move the first wish up or the last one down', async () => {
    mocks.listWishes.mockResolvedValue([
      wish({ wish_id: 'a', title: 'Chef knife', position: 0 }),
      wish({ wish_id: 'b', title: 'Cycling gloves', position: 1 }),
    ]);
    render(<WishListPanel groupId="g1" />);

    const first = await screen.findByLabelText('Move Chef knife up');
    const last = screen.getByLabelText('Move Cycling gloves down');

    expect(first.props.accessibilityState?.disabled).toBe(true);
    expect(last.props.accessibilityState?.disabled).toBe(true);
  });
});

describe('removing a wish', () => {
  it('takes two presses so a single tap cannot delete', async () => {
    mocks.listWishes.mockResolvedValue([wish({ wish_id: 'a', title: 'Chef knife' })]);
    render(<WishListPanel groupId="g1" />);

    fireEvent.press(await screen.findByLabelText('Remove Chef knife'));
    expect(mocks.deleteWish).not.toHaveBeenCalled();

    fireEvent.press(screen.getByLabelText('Confirm removing Chef knife'));
    await waitFor(() => expect(mocks.deleteWish).toHaveBeenCalledWith('token', 'g1', 'a'));
  });
});

describe('editing a wish', () => {
  it('opens with the saved values and sends the changed ones', async () => {
    mocks.listWishes.mockResolvedValue([
      wish({ wish_id: 'a', title: 'Chef knife', price_cents: 2599, currency: 'USD' }),
    ]);
    render(<WishListPanel groupId="g1" />);

    fireEvent.press(await screen.findByLabelText('Edit Chef knife'));

    // The accessible name is the field's label including its "(optional)" hint — a screen reader
    // says "Rough price, optional", which is the information someone needs.
    expect(screen.getByLabelText('Rough price (optional)').props.value).toBe('25.99');
    fireEvent.changeText(screen.getByLabelText('What is it?'), 'Better chef knife');
    fireEvent.press(screen.getByText('Save changes'));

    await waitFor(() => expect(mocks.updateWish).toHaveBeenCalled());
    expect(mocks.updateWish.mock.calls[0][3]).toMatchObject({ title: 'Better chef knife' });
  });

  // An edit sends empty strings for cleared fields; `undefined` would mean "leave alone" and a link
  // could never be removed once added.
  it('clears a link by sending an empty string rather than omitting it', async () => {
    mocks.listWishes.mockResolvedValue([
      wish({ wish_id: 'a', title: 'Chef knife', url: 'https://example.com/knife' }),
    ]);
    render(<WishListPanel groupId="g1" />);

    fireEvent.press(await screen.findByLabelText('Edit Chef knife'));
    fireEvent.changeText(screen.getByLabelText('Link (optional)'), '');
    fireEvent.press(screen.getByText('Save changes'));

    await waitFor(() => expect(mocks.updateWish).toHaveBeenCalled());
    expect(mocks.updateWish.mock.calls[0][3].url).toBe('');
  });
});

describe("the giver's view", () => {
  it('shows the wishes with no way to change them', () => {
    render(
      <RecipientWishList
        wishes={[
          {
            wish_id: 'a',
            kind: 'product',
            title: 'Chef knife',
            url: 'https://example.com/knife',
            image_url: null,
            price_cents: 2599,
            currency: 'USD',
            quantity: 1,
            priority: 'high',
            details: 'Any brand is fine',
            position: 0,
          },
        ]}
      />,
    );

    expect(screen.getByText('Chef knife')).toBeTruthy();
    expect(screen.getByText('25.99 USD')).toBeTruthy();
    expect(screen.getByText('Would love it')).toBeTruthy();
    // The hostname, not the tracking-laden URL.
    expect(screen.getByText('example.com ↗')).toBeTruthy();
    expect(screen.queryByLabelText('Edit Chef knife')).toBeNull();
    expect(screen.queryByLabelText('Remove Chef knife')).toBeNull();
  });

  // Would have failed before the casing fix: the API sends "product"/"high", and the app's unions
  // said "Product"/"High", so both badges rendered empty.
  it('labels the kind and priority the API actually sends', () => {
    render(
      <RecipientWishList
        wishes={[
          {
            wish_id: 'a',
            kind: 'product',
            title: 'Chef knife',
            url: null,
            image_url: null,
            price_cents: null,
            currency: null,
            quantity: 1,
            priority: 'high',
            details: null,
            position: 0,
          },
        ]}
      />,
    );

    expect(screen.getByText('To buy')).toBeTruthy();
    expect(screen.getByText('Would love it')).toBeTruthy();
  });

  it('says so plainly when the recipient added nothing', () => {
    render(<RecipientWishList wishes={[]} />);

    expect(screen.getByText('No specific wishes added.')).toBeTruthy();
  });
});

// Purchase claims (#130). The list is the only surface that renders them, and it renders them only
// when handed the handlers — which is how the emergency reveal and every other read-only path get
// none by omission rather than by remembering to strip them.
describe("the giver's purchase claims", () => {
  const claim = jest.fn();
  const release = jest.fn();

  function recipientWish(overrides: Partial<RecipientWish> = {}): RecipientWish {
    return {
      wish_id: 'a',
      kind: 'product',
      title: 'Chef knife',
      url: null,
      image_url: null,
      price_cents: null,
      currency: null,
      quantity: 1,
      priority: 'normal',
      details: null,
      position: 0,
      ...overrides,
    };
  }

  beforeEach(() => {
    claim.mockClear();
    release.mockClear();
  });

  it('offers both marks on an unclaimed wish, and says the mark is private', () => {
    render(<RecipientWishList wishes={[recipientWish()]} onClaim={claim} onRelease={release} />);

    expect(screen.getByText(/never see it, and it is only for this draw/)).toBeTruthy();
    fireEvent.press(screen.getByText("I'm getting this"));
    expect(claim).toHaveBeenCalledWith('a', 'planned', 1);

    fireEvent.press(screen.getByText('I bought it'));
    expect(claim).toHaveBeenCalledWith('a', 'purchased', 1);
    // Nothing to undo until something is claimed.
    expect(screen.queryByText('Undo')).toBeNull();
  });

  it('reads back a claim and lets it be released', () => {
    render(
      <RecipientWishList
        wishes={[recipientWish({ claim: { state: 'purchased', quantity: 1, updated_at: 'now' } })]}
        onClaim={claim}
        onRelease={release}
      />,
    );

    expect(screen.getByText('You bought this')).toBeTruthy();
    // Already bought: there is no further mark to make, only an undo.
    expect(screen.queryByText('I bought it')).toBeNull();
    expect(screen.queryByText("I'm getting this")).toBeNull();

    fireEvent.press(screen.getByText('Undo'));
    expect(release).toHaveBeenCalledWith('a');
  });

  it('claims the whole quantity by default and reports a partial one', () => {
    const { rerender } = render(
      <RecipientWishList wishes={[recipientWish({ quantity: 3 })]} onClaim={claim} onRelease={release} />,
    );

    fireEvent.press(screen.getByText('I bought it'));
    expect(claim).toHaveBeenCalledWith('a', 'purchased', 3);

    rerender(
      <RecipientWishList
        wishes={[recipientWish({ quantity: 3, claim: { state: 'planned', quantity: 2, updated_at: 'now' } })]}
        onClaim={claim}
        onRelease={release}
      />,
    );
    expect(screen.getByText('You are getting this · 2 of 3')).toBeTruthy();
  });

  /**
   * The read-only path. Without handlers there is no control to press — which is what the emergency
   * reveal renders, and what an owner's own list could never render anyway because `Wish` carries
   * no claim.
   */
  it('renders nothing about claims when it is not given the handlers', () => {
    render(
      <RecipientWishList
        wishes={[recipientWish({ claim: { state: 'purchased', quantity: 1, updated_at: 'now' } })]}
      />,
    );

    expect(screen.getByText('Chef knife')).toBeTruthy();
    expect(screen.queryByText('You bought this')).toBeNull();
    expect(screen.queryByText('I bought it')).toBeNull();
    expect(screen.queryByText(/never see it/)).toBeNull();
  });
});

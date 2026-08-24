// The wishlist editor. Covers the interactions someone actually performs on their own list, and the
// two rules that matter beyond the UI: a reorder sends a complete order, and the giver's view is
// read-only.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import type { Wish } from '../types';

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
    kind: 'Product',
    url: null,
    image_url: null,
    price_cents: null,
    currency: null,
    quantity: 1,
    priority: 'Normal',
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
            kind: 'Product',
            title: 'Chef knife',
            url: 'https://example.com/knife',
            image_url: null,
            price_cents: 2599,
            currency: 'USD',
            quantity: 1,
            priority: 'High',
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

  it('says so plainly when the recipient added nothing', () => {
    render(<RecipientWishList wishes={[]} />);

    expect(screen.getByText('No specific wishes added.')).toBeTruthy();
  });
});

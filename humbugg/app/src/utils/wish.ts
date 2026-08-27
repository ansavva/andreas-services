import type { CreateWishInput, WishKind, WishPriority } from '../types';

export const wishKinds: { value: WishKind; label: string }[] = [
  { value: 'Product', label: 'Something to buy' },
  { value: 'Custom', label: 'An idea, not a product' },
  { value: 'Experience', label: 'An experience' },
  { value: 'Charity', label: 'A donation' },
];

export const wishPriorities: { value: WishPriority; label: string }[] = [
  { value: 'High', label: 'Would love it' },
  { value: 'Normal', label: 'Happy either way' },
  { value: 'Low', label: 'Only if it is easy' },
];

export const priorityLabel: Record<WishPriority, string> = {
  High: 'Would love it',
  Normal: 'Happy either way',
  Low: 'Only if it is easy',
};

export const kindLabel: Record<WishKind, string> = {
  Product: 'To buy',
  Custom: 'Idea',
  Experience: 'Experience',
  Charity: 'Donation',
};

export interface WishFormValues {
  title: string;
  kind: WishKind;
  url: string;
  imageUrl: string;
  price: string;
  quantity: string;
  priority: WishPriority;
  details: string;
}

export const emptyWishForm: WishFormValues = {
  title: '',
  kind: 'Product',
  url: '',
  imageUrl: '',
  price: '',
  quantity: '1',
  priority: 'Normal',
  details: '',
};

/**
 * Money arrives from the person as a decimal string and leaves for the API as an integer of minor
 * units. Parsing here rather than at the input keeps a half-typed "12." from being read as a number
 * while someone is still typing it.
 */
export function parsePrice(value: string): { cents?: number; error?: string } {
  const trimmed = value.trim();
  if (trimmed.length === 0) return {};
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(trimmed))
    return { error: 'Price must be a number, with at most two decimal places.' };
  return { cents: Math.round(Number(trimmed) * 100) };
}

export function formatPrice(cents: number | null | undefined, currency: string | null | undefined) {
  if (cents == null) return null;
  const amount = (cents / 100).toFixed(2);
  return currency ? `${amount} ${currency}` : amount;
}

/**
 * The hostname alone, so a giver can see where a link goes before following it. Shown instead of the
 * raw URL because a long tracking-laden product URL tells them nothing and wraps badly on a phone.
 */
export function linkHost(url: string | null | undefined) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

/**
 * Mirrors the server's rules so the person is told at the point of typing rather than after a round
 * trip. The server still validates — this is a courtesy, not the boundary.
 */
export function validateWishForm(values: WishFormValues): string | null {
  if (values.title.trim().length === 0) return 'Give the wish a name.';
  if (values.title.trim().length > 200) return 'The name must be 200 characters or fewer.';
  for (const [label, value] of [['link', values.url], ['image link', values.imageUrl]] as const) {
    const trimmed = value.trim();
    if (trimmed.length === 0) continue;
    if (!/^https?:\/\//i.test(trimmed)) return `The ${label} must start with http:// or https://.`;
    try { new URL(trimmed); } catch { return `That ${label} is not a complete web address.`; }
  }
  const quantity = Number(values.quantity.trim() || '1');
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 99)
    return 'Quantity must be a whole number between 1 and 99.';
  const price = parsePrice(values.price);
  if (price.error) return price.error;
  if (values.details.trim().length > 1000) return 'Notes must be 1000 characters or fewer.';
  return null;
}

/** Only what the person filled in — an untouched optional field is left absent, not sent empty. */
export function toCreateInput(values: WishFormValues): CreateWishInput {
  const price = parsePrice(values.price);
  return {
    title: values.title.trim(),
    kind: values.kind,
    priority: values.priority,
    quantity: Number(values.quantity.trim() || '1'),
    ...(values.url.trim() ? { url: values.url.trim() } : {}),
    ...(values.imageUrl.trim() ? { image_url: values.imageUrl.trim() } : {}),
    ...(price.cents != null ? { price_cents: price.cents } : {}),
    ...(values.details.trim() ? { details: values.details.trim() } : {}),
  };
}

/**
 * An edit sends every editable field, including the ones now empty — that is how a person clears a
 * link or a price they no longer want. `undefined` would mean "leave alone" and the field could
 * never be emptied.
 */
export function toUpdateInput(values: WishFormValues) {
  const price = parsePrice(values.price);
  return {
    title: values.title.trim(),
    kind: values.kind,
    priority: values.priority,
    quantity: Number(values.quantity.trim() || '1'),
    url: values.url.trim(),
    image_url: values.imageUrl.trim(),
    details: values.details.trim(),
    ...(price.cents != null ? { price_cents: price.cents } : {}),
  };
}

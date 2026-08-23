export interface GroupFormValues {
  name: string;
  description: string;
  eventDate: string;
  signupDeadline: string;
  spendingLimit: string;
}

export interface AddressFormValues {
  line1: string;
  line2: string;
  city: string;
  region: string;
  postalCode: string;
  country: string;
}

export function todayInputValue(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function validateGroupForm(values: GroupFormValues, today = todayInputValue()): string | null {
  const name = values.name.trim();
  if (!name) return 'Enter a group name.';
  if (name.length > 120) return 'Group names must be 120 characters or fewer.';
  if (values.description.trim().length > 1000) return 'Group notes must be 1,000 characters or fewer.';
  if (values.eventDate && values.eventDate < today) return 'The event date cannot be in the past.';
  if (values.signupDeadline && values.signupDeadline < today) return 'The join-by date cannot be in the past.';
  if (values.eventDate && values.signupDeadline && values.signupDeadline > values.eventDate)
    return 'The join-by date must be on or before the event date.';

  if (values.spendingLimit) {
    if (!/^\d+(?:\.\d{1,2})?$/.test(values.spendingLimit))
      return 'The spending limit can use at most two decimal places.';
    const amount = Number(values.spendingLimit);
    if (!Number.isFinite(amount) || amount < 0.01 || amount > 100_000)
      return 'The spending limit must be between $0.01 and $100,000.';
  }
  return null;
}

export function validateAddressForm(values: AddressFormValues): string | null {
  const populated = Object.values(values).some((value) => value.trim().length > 0);
  if (!populated) return null;
  if (!values.line1.trim() || !values.city.trim() || !values.postalCode.trim() || !values.country.trim())
    return 'A mailing address needs an address line, city, postal code, and country.';
  return null;
}

export function validatePassword(password: string): string | null {
  if (password.length < 12) return 'Use at least 12 characters.';
  if (!/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password))
    return 'Include an uppercase letter, a lowercase letter, and a number.';
  return null;
}

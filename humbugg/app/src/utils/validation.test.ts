// Ported verbatim from the web app apart from the runner: `describe`/`it`/`expect`
// are Jest globals here rather than vitest imports.
import { todayInputValue, validateAddressForm, validateGroupForm, validatePassword } from './validation';

const validGroup = {
  name: 'Family exchange',
  description: '',
  eventDate: '2030-12-25',
  signupDeadline: '2030-12-10',
  spendingLimit: '50.00',
};

describe('group form validation', () => {
  it('rejects past dates', () => {
    expect(validateGroupForm({ ...validGroup, eventDate: '2029-12-25' }, '2030-01-01')).toContain('past');
    expect(validateGroupForm({ ...validGroup, signupDeadline: '2029-12-25' }, '2030-01-01')).toContain('past');
  });

  it('requires the join-by date to be no later than the event', () => {
    expect(validateGroupForm({ ...validGroup, signupDeadline: '2030-12-26' }, '2030-01-01')).toContain('on or before');
  });

  it('rejects invalid money and accepts valid boundaries', () => {
    expect(validateGroupForm({ ...validGroup, spendingLimit: '1.001' }, '2030-01-01')).toContain('decimal');
    expect(validateGroupForm({ ...validGroup, spendingLimit: '0' }, '2030-01-01')).toContain('$0.01');
    expect(validateGroupForm({ ...validGroup, spendingLimit: '0.01' }, '2030-01-01')).toBeNull();
  });
});

describe('address and account validation', () => {
  it('allows an empty address but rejects an unusable partial address', () => {
    const empty = { line1: '', line2: '', city: '', region: '', postalCode: '', country: '' };
    expect(validateAddressForm(empty)).toBeNull();
    expect(validateAddressForm({ ...empty, city: 'Boston' })).toContain('address line');
  });

  it('matches the Cognito password policy', () => {
    expect(validatePassword('passwordpassword')).toContain('uppercase');
    expect(validatePassword('Password123')).toContain('12 characters');
    expect(validatePassword('Password1234')).toBeNull();
  });

  it('formats local dates for date-input minimums', () => {
    expect(todayInputValue(new Date(2030, 0, 2, 12))).toBe('2030-01-02');
  });
});

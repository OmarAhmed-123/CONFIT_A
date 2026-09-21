import { describe, it, expect } from 'vitest';
import { validateCheckoutSubmission, isValidEmail } from '../checkoutValidation';
import { isMessageDescriptor, type TranslatableMessage } from '../../i18n/messages';

/** Assert on the KEY, not on English prose — the message is localized now. */
function expectKey(message: TranslatableMessage | undefined, key: string) {
  expect(isMessageDescriptor(message)).toBe(true);
  expect((message as { key: string }).key).toBe(key);
}

const base = {
  isAuthenticated: false,
  itemsCount: 1,
  guestEmail: '',
  fulfillmentType: 'delivery' as const,
  bopisStoreId: null,
  addressLine: '12 Nile Street',
  recipientName: 'QA Bot',
  phone: '+201000000000',
};

describe('isValidEmail', () => {
  it('accepts normal addresses', () => {
    expect(isValidEmail('user@example.com')).toBe(true);
    expect(isValidEmail('  user@example.com  ')).toBe(true);
  });
  it('rejects malformed addresses', () => {
    for (const bad of ['nope', 'a@b', 'a b@c.com', '@x.com', 'a@.com']) {
      expect(isValidEmail(bad)).toBe(false);
    }
  });
});

describe('validateCheckoutSubmission', () => {
  it('passes for a complete guest delivery order', () => {
    expect(validateCheckoutSubmission({ ...base, guestEmail: 'guest@x.com' })).toEqual({ ok: true });
  });

  it('fails with guest_email field when the guest has no email (P0-01 regression)', () => {
    const r = validateCheckoutSubmission(base);
    expect(r.ok).toBe(false);
    expect(r.field).toBe('guest_email');
    expectKey(r.message, 'errors.guest_email_required');
  });

  it('fails with guest_email field for a malformed email', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'not-an-email' });
    expect(r.field).toBe('guest_email');
    expectKey(r.message, 'errors.email_invalid');
  });

  it('skips the email requirement when authenticated', () => {
    const r = validateCheckoutSubmission({ ...base, isAuthenticated: true });
    expect(r.ok).toBe(true);
  });

  it('fails on empty bag regardless of everything else', () => {
    const r = validateCheckoutSubmission({ ...base, itemsCount: 0, guestEmail: 'g@x.com' });
    expect(r.field).toBe('cart');
    expectKey(r.message, 'errors.empty_bag');
  });

  it('requires a BOPIS store when pickup is selected', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', fulfillmentType: 'bopis' });
    expect(r.field).toBe('bopis_store');
    expectKey(r.message, 'errors.store_required');
  });

  it('requires an address for delivery', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', addressLine: '  ' });
    expect(r.field).toBe('address');
    expectKey(r.message, 'errors.address_required');
  });

  it('requires recipient name and phone', () => {
    const noName = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', recipientName: ' ' });
    expect(noName.field).toBe('recipient_name');
    expectKey(noName.message, 'errors.recipient_required');
    const noPhone = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', phone: '' });
    expect(noPhone.field).toBe('phone');
    expectKey(noPhone.message, 'errors.phone_required');
  });
});

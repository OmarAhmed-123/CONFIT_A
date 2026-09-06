import { describe, it, expect } from 'vitest';
import { validateCheckoutSubmission, isValidEmail } from '../checkoutValidation';

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
    expect(r.message).toMatch(/guest checkout/i);
  });

  it('fails with guest_email field for a malformed email', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'not-an-email' });
    expect(r.field).toBe('guest_email');
    expect(r.message).toMatch(/invalid/i);
  });

  it('skips the email requirement when authenticated', () => {
    const r = validateCheckoutSubmission({ ...base, isAuthenticated: true });
    expect(r.ok).toBe(true);
  });

  it('fails on empty bag regardless of everything else', () => {
    const r = validateCheckoutSubmission({ ...base, itemsCount: 0, guestEmail: 'g@x.com' });
    expect(r.field).toBe('cart');
  });

  it('requires a BOPIS store when pickup is selected', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', fulfillmentType: 'bopis' });
    expect(r.field).toBe('bopis_store');
  });

  it('requires an address for delivery', () => {
    const r = validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', addressLine: '  ' });
    expect(r.field).toBe('address');
  });

  it('requires recipient name and phone', () => {
    expect(
      validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', recipientName: ' ' }).field
    ).toBe('recipient_name');
    expect(validateCheckoutSubmission({ ...base, guestEmail: 'g@x.com', phone: '' }).field).toBe('phone');
  });
});
